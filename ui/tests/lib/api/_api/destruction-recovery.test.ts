import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestDestructionRecoveryPlan } from '$lib/api/_api/destruction-recovery';

describe('destruction recovery API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given a failed invocation when creating recovery then no client scope is submitted', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response(JSON.stringify({ planId: 'recovery-1' })))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestDestructionRecoveryPlan('run/one');

		expect(fetchMock).toHaveBeenCalledWith('/api/runs/run%2Fone/recovery-plan', {
			method: 'POST'
		});
	});
});
