import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchTopics } from '$lib/topic-browser/_api/fetch-topics';
import type { TopicsPayload } from '$lib/topic-browser/types';

describe('topic API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given broker inventory when topics are requested then the typed inventory is returned', async () => {
		const payload: TopicsPayload = {
			available: true,
			reason: null,
			pendingBrokers: [],
			topics: []
		};
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)));
		vi.stubGlobal('fetch', fetchMock);
		const controller: AbortController = new AbortController();

		const result: TopicsPayload = await fetchTopics(controller.signal);

		expect(result).toEqual(payload);
		expect(fetchMock).toHaveBeenCalledWith('/api/topics', { signal: controller.signal });
	});
});
