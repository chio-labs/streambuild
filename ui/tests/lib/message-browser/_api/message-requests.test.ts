import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	fetchMessageFacets,
	fetchMessageRecord,
	fetchMessages
} from '$lib/message-browser/_api/message-requests';
import type {
	FacetsPayload,
	MessageFilterDocument,
	MessageRecord,
	MessagesPayload
} from '$lib/message-browser/types';

describe('message browser API', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('given message operations when requested then each typed endpoint receives its payload', async () => {
		const messages: MessagesPayload = { rows: [], nextCursor: null, windowSeconds: null, limit: 50 };
		const record: MessageRecord = {
			landedAt: '2026-08-11 12:00:00', kafkaTimestamp: null, partition: 1, offset: 2,
			topic: 'orders', key: 'a', keyBytes: 1, value: '{}', valueBytes: 2,
			valueTruncated: false, headers: []
		};
		const facets: FacetsPayload = { values: [], nullCount: 0, otherCount: 0, totalCount: 0, windowSeconds: null };
		const fetchMock: ReturnType<typeof vi.fn> = vi.fn()
			.mockResolvedValueOnce(new Response(JSON.stringify(messages)))
			.mockResolvedValueOnce(new Response(JSON.stringify(record)))
			.mockResolvedValueOnce(new Response(JSON.stringify(facets)));
		vi.stubGlobal('fetch', fetchMock);
		const document: MessageFilterDocument = { mode: { kind: 'newest' }, predicates: [], limit: 50, timeColumn: 'landed', previewPaths: [] };
		const controller: AbortController = new AbortController();

		await fetchMessages('order feed', document, null, controller.signal);
		await fetchMessageRecord('order feed', 1, 2);
		await fetchMessageFacets('order feed', document, ['kind'], controller.signal);

		expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/sources/order%20feed/messages', expect.objectContaining({ method: 'POST' }));
		expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/sources/order%20feed/messages/record', expect.objectContaining({ body: JSON.stringify({ partition: 1, offset: 2 }) }));
		expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/sources/order%20feed/messages/facets', expect.objectContaining({ signal: controller.signal }));
	});
});
