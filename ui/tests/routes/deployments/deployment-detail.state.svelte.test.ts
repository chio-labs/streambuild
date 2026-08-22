import { describe, expect, it, vi } from 'vitest';

import type { DeploymentDetail } from '$lib/domain/types';

const requests: { fetchDeployment: ReturnType<typeof vi.fn> } = vi.hoisted(() => ({
	fetchDeployment: vi.fn()
}));

vi.mock('$lib/api/main/deployments/fetch-deployment', () => ({
	fetchDeployment: requests.fetchDeployment
}));

import { createDeploymentDetailState } from '../../../src/routes/deployments/[id]/state.svelte';
import type { DeploymentDetailState } from '../../../src/routes/deployments/[id]/types';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
	let resolve!: (value: T) => void;
	const promise: Promise<T> = new Promise((done) => {
		resolve = done;
	});
	return { promise, resolve };
}

function detail(deploymentId: string): DeploymentDetail {
	return { deploymentId } as DeploymentDetail;
}

describe('deployment detail state', () => {
	it('given rapid navigation when details resolve then stale data cannot replace the current deployment', async () => {
		const first = deferred<DeploymentDetail>();
		const second = deferred<DeploymentDetail>();
		requests.fetchDeployment.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
		const state: DeploymentDetailState = createDeploymentDetailState();

		const firstLoad: Promise<void> = state.load('first');
		const firstSignal: AbortSignal = requests.fetchDeployment.mock.calls[0][1];
		expect(state.loading).toBe(true);

		const secondLoad: Promise<void> = state.load('second');
		expect(firstSignal.aborted).toBe(true);
		expect(state.requestedId).toBe('second');
		second.resolve(detail('second'));
		await secondLoad;

		expect(state.detail?.deploymentId).toBe('second');
		expect(state.loading).toBe(false);

		first.resolve(detail('first'));
		await firstLoad;
		expect(state.detail?.deploymentId).toBe('second');
	});
});
