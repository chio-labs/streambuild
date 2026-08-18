import { describe, expect, it, vi } from 'vitest';

import type { AppController } from '$lib/api/types';

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

describe('application state', () => {
	it('given an unreachable status endpoint when initialized then the application records the failure', async () => {
		requests.requestStatusPayload.mockRejectedValueOnce(new Error('backend offline'));
		const controller: AppController = createAppState();

		await controller.initialize();

		expect(controller.app.phase).toBe('unreachable');
		expect(controller.app.fetchError).toContain('backend offline');
	});
});
