import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	requestDeployment,
	requestDeploymentDiff,
	requestDeployments
} from '$lib/api/_api/deployments';
import type { Deployment } from '$lib/domain/types';

describe('deployments API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given deployment identifiers when records and diffs are requested then paths are encoded and lists are unwrapped', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi
			.fn()
			.mockResolvedValueOnce(new Response('{"deployments":[]}'))
			.mockResolvedValueOnce(new Response('{}'))
			.mockResolvedValueOnce(new Response('{}'))
			.mockResolvedValueOnce(new Response('{}'));
		vi.stubGlobal('fetch', fetchMock);

		const deployments: Deployment[] = await requestDeployments();
		await requestDeployment('candidate/id');
		await requestDeploymentDiff('candidate/id', null);
		await requestDeploymentDiff('candidate/id', 'base/id');

		expect(deployments).toEqual([]);
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/deployments/candidate%2Fid');
		expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/deployments/candidate%2Fid/diff');
		expect(fetchMock).toHaveBeenNthCalledWith(
			4,
			'/api/deployments/candidate%2Fid/diff?against=base%2Fid'
		);
	});
});
