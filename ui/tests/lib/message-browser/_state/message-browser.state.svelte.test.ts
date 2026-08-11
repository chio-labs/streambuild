import { describe, expect, it, vi } from 'vitest';

import type { FacetsPayload, MessagesPayload } from '$lib/message-browser/types';

const requests: {
	fetchMessageFacets: ReturnType<typeof vi.fn>;
	fetchMessages: ReturnType<typeof vi.fn>;
} = vi.hoisted(() => ({ fetchMessageFacets: vi.fn(), fetchMessages: vi.fn() }));

vi.mock('$lib/message-browser/_api/message-requests', () => ({
	fetchMessageFacets: requests.fetchMessageFacets,
	fetchMessages: requests.fetchMessages
}));

import { createMessageBrowserState } from '$lib/message-browser/_state/message-browser.state.svelte';
import type { MessageBrowserState } from '$lib/message-browser/types';

describe('message browser state', () => {
	it('given a source when messages load then rows, cursor, and facets are exposed together', async () => {
		const messages: MessagesPayload = { rows: [], nextCursor: null, windowSeconds: 3600, limit: 50 };
		const facets: FacetsPayload = { values: [], nullCount: 0, otherCount: 0, totalCount: 0, windowSeconds: 3600 };
		requests.fetchMessages.mockResolvedValueOnce(messages);
		requests.fetchMessageFacets.mockResolvedValueOnce(facets);
		const state: MessageBrowserState = createMessageBrowserState('state-test-source');

		await state.ensureLoaded();

		expect(state.rows).toEqual([]);
		expect(state.windowSeconds).toBe(3600);
		expect(state.facets).toEqual(facets);
	});
});
