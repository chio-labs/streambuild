import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestStoredDestructionPlan } from '$lib/api/_api/destruction-plan';

describe('stored destruction plan API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a plan ID when reading then the actor-bound endpoint is used', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response(JSON.stringify({ planId: 'plan/one' })))
		);
		vi.stubGlobal('fetch', fetchMock);
		const controller: AbortController = new AbortController();

		await requestStoredDestructionPlan('plan/one', controller.signal);

		expect(fetchMock).toHaveBeenCalledWith('/api/destruction/plans/plan%2Fone', {
			signal: controller.signal
		});
	});
});
