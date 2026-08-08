import { readApiResponse } from '$lib/api';
import type {
	FacetsPayload,
	MessageCursor,
	MessageFilterDocument,
	MessageRecord,
	MessagesPayload
} from './types';

/** Query one page of messages for a managed source under the current filter document. */
export async function fetchMessages(
	sourceName: string,
	document: MessageFilterDocument,
	cursor: MessageCursor | null,
	signal: AbortSignal
): Promise<MessagesPayload> {
	const response = await fetch(`/api/sources/${encodeURIComponent(sourceName)}/messages`, {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ ...document, cursor }),
		signal
	});
	return readApiResponse<MessagesPayload>(response, 'message query');
}

/** Fetch one full record by replay coordinates for the accordion detail. */
export async function fetchMessageRecord(
	sourceName: string,
	partition: number,
	offset: number
): Promise<MessageRecord> {
	const response = await fetch(
		`/api/sources/${encodeURIComponent(sourceName)}/messages/record`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ partition, offset })
		}
	);
	return readApiResponse<MessageRecord>(response, 'message record');
}

/** Fetch top facet values inside the current filter document. */
export async function fetchMessageFacets(
	sourceName: string,
	document: MessageFilterDocument,
	facetPath: (string | number)[],
	signal: AbortSignal
): Promise<FacetsPayload> {
	const response = await fetch(
		`/api/sources/${encodeURIComponent(sourceName)}/messages/facets`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ ...document, cursor: null, facetPath }),
			signal
		}
	);
	return readApiResponse<FacetsPayload>(response, 'message facets');
}
