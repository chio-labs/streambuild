import { afterEach, describe, expect, it, vi } from 'vitest';

import { requestInactivePipelines } from '$lib/inactive-pipelines/_api/request-inactive-pipelines';

describe('inactive pipeline API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given retained ownership when inactive pipelines are requested then summaries are returned', async () => {
		const pipelines: Awaited<ReturnType<typeof requestInactivePipelines>> = [
			{
				name: 'retired_orders',
				modelCount: 2,
				resourceCount: 5,
				lastPublishedAt: '2026-08-23 10:00:00.000000'
			}
		];
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn(() =>
			Promise.resolve(new Response(JSON.stringify({ pipelines })))
		);
		vi.stubGlobal('fetch', fetchMock);

		const result: Awaited<ReturnType<typeof requestInactivePipelines>> =
			await requestInactivePipelines();

		expect(fetchMock).toHaveBeenCalledWith('/api/destruction/pipelines/inactive', {});
		expect(result).toEqual(pipelines);
	});
});
