import { describe, expect, it, vi } from 'vitest';

import type { TopicsPayload } from '$lib/topic-browser/types';

const requests: { fetchTopics: ReturnType<typeof vi.fn> } = vi.hoisted(() => ({
	fetchTopics: vi.fn()
}));

vi.mock('$lib/topic-browser/_api/fetch-topics', () => ({ fetchTopics: requests.fetchTopics }));
vi.mock('$lib/topic-browser/_resources/topic-polling.resource', () => ({
	createTopicPollingResource: vi.fn(() => ({ start: vi.fn(), stop: vi.fn() }))
}));

import { createTopicBrowserState } from '$lib/topic-browser/_state/topic-browser.state.svelte';
import type { TopicBrowserState } from '$lib/topic-browser/types';

describe('topic browser state', () => {
	it('given uncached inventory when loading is ensured then topics become available', async () => {
		const payload: TopicsPayload = {
			available: true,
			reason: null,
			pendingBrokers: [],
			topics: []
		};
		requests.fetchTopics.mockResolvedValueOnce(payload);
		const state: TopicBrowserState = createTopicBrowserState();

		await state.ensureLoaded();

		expect(state.payload).toEqual(payload);
		expect(state.error).toBeNull();
	});
});
