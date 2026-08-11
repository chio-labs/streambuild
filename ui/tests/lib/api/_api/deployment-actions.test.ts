import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	requestDeploymentCleanup,
	requestDeploymentPromotion
} from '$lib/api/_api/deployment-actions';

describe('deployment action API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given deployment actions when requested then promotion and cleanup use their exact payloads', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestDeploymentPromotion('candidate/id');
		await requestDeploymentCleanup(14);

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/deployments/candidate%2Fid/promote', {
			method: 'POST'
		});
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/deployments/cleanup', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ retentionDays: 14 })
		});
	});
});
