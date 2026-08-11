import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestBuildFeed, requestBuildStart, requestRunEvents } from '$lib/api/_api/build';

describe('build API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given build inputs when build endpoints are requested then transport preserves their contract', async () => {
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response('{}'))
		);
		vi.stubGlobal('fetch', fetchMock);

		await requestBuildStart(
			['model:orders'],
			'2026-08-10T12:00:00Z',
			['breaking-change'],
			'20260811T120000Z_plan'
		);
		await requestBuildFeed(17);
		await requestRunEvents('run/id', 23);

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/build', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				selectors: ['model:orders'],
				startTime: '2026-08-10T12:00:00Z',
				deploymentId: '20260811T120000Z_plan',
				confirmations: ['breaking-change']
			})
		});
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/build/current?after=17');
		expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/runs/run%2Fid/events?after=23');
	});
});
