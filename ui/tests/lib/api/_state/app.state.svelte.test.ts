import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AppController, BootstrapPayload } from '$lib/api/types';
import type { Project } from '$lib/domain/types';

type MockFunction = ReturnType<typeof vi.fn>;
type RequestMocks = {
	requestDeployments: MockFunction;
	requestProjectReload: MockFunction;
	requestWarehouseRefresh: MockFunction;
	requestDefinitionsPayload: MockFunction;
	requestStatePayload: MockFunction;
	requestStatusPayload: MockFunction;
	requestCheckStatuses: MockFunction;
};

const requests: RequestMocks = vi.hoisted(() => ({
	requestDeployments: vi.fn(),
	requestProjectReload: vi.fn(),
	requestWarehouseRefresh: vi.fn(),
	requestDefinitionsPayload: vi.fn(),
	requestStatePayload: vi.fn(),
	requestStatusPayload: vi.fn(),
	requestCheckStatuses: vi.fn()
}));

vi.mock('$lib/api/_api/deployments', () => ({
	requestDeployments: requests.requestDeployments
}));
vi.mock('$lib/api/_api/project-actions', () => ({
	requestProjectReload: requests.requestProjectReload,
	requestWarehouseRefresh: requests.requestWarehouseRefresh
}));
vi.mock('$lib/api/_api/project', () => ({
	requestDefinitionsPayload: requests.requestDefinitionsPayload,
	requestStatePayload: requests.requestStatePayload,
	requestStatusPayload: requests.requestStatusPayload
}));
vi.mock('$lib/api/_api/quality', () => ({
	requestCheckStatuses: requests.requestCheckStatuses
}));
vi.mock('$lib/api/_helpers/mapping', () => ({
	applyRecordedCheckStatuses: vi.fn(),
	projectFromServer: vi.fn()
}));
vi.mock('$lib/api/_resources/kafka-lag-retry.resource', () => ({
	createKafkaLagRetryResource: vi.fn(() => ({ schedule: vi.fn(), reset: vi.fn() }))
}));
vi.mock('$lib/api/_resources/polling.resource', () => ({
	createPollingResource: vi.fn(() => ({ start: vi.fn(), stop: vi.fn() }))
}));
vi.mock('$lib/api/_resources/visibility.resource', () => ({
	createVisibilityResource: vi.fn(() => ({ start: vi.fn(), stop: vi.fn() }))
}));

import { createAppState } from '$lib/api/_state/app.state.svelte';
import { projectFromServer } from '$lib/api/_helpers/mapping';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
	let resolvePromise: (value: T) => void = () => undefined;
	const promise: Promise<T> = new Promise((resolve) => {
		resolvePromise = resolve;
	});
	return { promise, resolve: resolvePromise };
}

describe('application state', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		requests.requestStatusPayload.mockResolvedValue({
			compile: { state: 'ok', versionKey: 'version-1' },
			warehouse: { connected: true }
		});
		requests.requestDefinitionsPayload.mockResolvedValue({});
		requests.requestStatePayload.mockResolvedValue({});
		requests.requestDeployments.mockResolvedValue([]);
		requests.requestCheckStatuses.mockResolvedValue([]);
		vi.mocked(projectFromServer).mockReturnValue({ audits: [], tests: [] } as unknown as Project);
	});

	it('given an unreachable status endpoint when initialized then the application records the failure', async () => {
		requests.requestStatusPayload.mockRejectedValueOnce(new Error('backend offline'));
		const controller: AppController = createAppState();

		await controller.initialize();

		expect(controller.app.phase).toBe('unreachable');
		expect(controller.app.fetchError).toContain('backend offline');
	});

	it('given slow secondary data when initialized then the application renders without waiting', async () => {
		const deployments = deferred<[]>();
		const checks = deferred<[]>();
		requests.requestDeployments.mockReturnValue(deployments.promise);
		requests.requestCheckStatuses.mockReturnValue(checks.promise);
		const controller: AppController = createAppState();

		await controller.initialize();

		expect(controller.app.phase).toBe('ready');
		expect(requests.requestDeployments).toHaveBeenCalledOnce();
		expect(requests.requestCheckStatuses).toHaveBeenCalledOnce();
		deployments.resolve([]);
		checks.resolve([]);
	});

	it('given an active deployment refresh when another starts then one request serves both callers', async () => {
		const deployments = deferred<[]>();
		requests.requestDeployments.mockReturnValue(deployments.promise);
		const controller: AppController = createAppState();

		const first: Promise<void> = controller.refreshDeployments();
		const second: Promise<void> = controller.refreshDeployments();
		deployments.resolve([]);
		await Promise.all([first, second]);

		expect(requests.requestDeployments).toHaveBeenCalledOnce();
	});

	it('given overlapping live triggers when the version is unchanged then one status request reuses definitions', async () => {
		const controller: AppController = createAppState();
		await controller.initialize();
		vi.clearAllMocks();
		const status = deferred<Record<string, unknown>>();
		requests.requestStatusPayload.mockReturnValue(status.promise);
		requests.requestStatePayload.mockResolvedValue({});

		const timerRefresh: Promise<void> = controller.refreshLiveState();
		const visibilityRefresh: Promise<void> = controller.refreshLiveState();
		status.resolve({
			compile: { state: 'ok', versionKey: 'version-1' },
			warehouse: { connected: true }
		});
		await Promise.all([timerRefresh, visibilityRefresh]);

		expect(requests.requestStatusPayload).toHaveBeenCalledOnce();
		expect(requests.requestStatePayload).toHaveBeenCalledOnce();
		expect(requests.requestDefinitionsPayload).not.toHaveBeenCalled();
	});

	it('given slow quality status when forcing a snapshot refresh then refresh completes without waiting', async () => {
		const checks = deferred<[]>();
		requests.requestWarehouseRefresh.mockResolvedValue({
			compile: { state: 'ok', versionKey: 'version-1' },
			warehouse: { connected: true }
		});
		requests.requestCheckStatuses.mockReturnValue(checks.promise);
		const controller: AppController = createAppState();
		controller.initializeFromBootstrap({
			auth: {
				config: { mode: 'disabled', loginRequired: false, proxyLogoutUrl: null },
				session: {
					mode: 'disabled',
					user: {
						id: '00000000-0000-4000-8000-000000000001',
						username: 'local',
						displayName: 'Local user',
						email: null,
						authenticationSource: 'local'
					},
					roles: ['admin'],
					csrfToken: null
				},
				capabilities: null
			},
			status: { compile: { state: 'ok' }, warehouse: { connected: true } },
			definitions: {},
			state: {}
		});
		vi.clearAllMocks();

		await controller.refreshLiveState({ force: true });

		expect(requests.requestWarehouseRefresh).toHaveBeenCalledOnce();
		expect(requests.requestCheckStatuses).toHaveBeenCalledOnce();
		checks.resolve([]);
	});

	it('given bootstrap project data when initialized then legacy project requests are skipped', () => {
		const controller: AppController = createAppState();
		const bootstrap: BootstrapPayload = {
			auth: {
				config: { mode: 'disabled', loginRequired: false, proxyLogoutUrl: null },
				session: {
					mode: 'disabled',
					user: {
						id: '00000000-0000-4000-8000-000000000001',
						username: 'local',
						displayName: 'Local user',
						email: null,
						authenticationSource: 'local'
					},
					roles: ['admin'],
					csrfToken: null
				},
				capabilities: null
			},
			status: { compile: { state: 'ok' }, warehouse: { connected: true } },
			definitions: {},
			state: {}
		};

		controller.initializeFromBootstrap(bootstrap);

		expect(controller.app.phase).toBe('ready');
		expect(requests.requestStatusPayload).not.toHaveBeenCalled();
		expect(requests.requestDefinitionsPayload).not.toHaveBeenCalled();
		expect(requests.requestStatePayload).not.toHaveBeenCalled();
	});
});
