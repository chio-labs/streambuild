import { readApiResponse } from '$lib/api/main/response/read-api-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';
import type {
	FacetsPayload,
	MessageCursor,
	MessageFilterDocument,
	MessageRecord,
	MessagesPayload
} from '$lib/message-browser/types';

export async function fetchMessages(
	sourceName: string,
	document: MessageFilterDocument,
	cursor: MessageCursor | null,
	signal: AbortSignal
): Promise<MessagesPayload> {
	const response: Response = await authenticatedFetch(
		`/api/sources/${encodeURIComponent(sourceName)}/messages`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ ...document, cursor }),
			signal
		}
	);
	return readApiResponse<MessagesPayload>(response, 'message query');
}

export async function fetchMessageRecord(
	sourceName: string,
	partition: number,
	offset: number
): Promise<MessageRecord> {
	const response: Response = await authenticatedFetch(
		`/api/sources/${encodeURIComponent(sourceName)}/messages/record`,
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ partition, offset })
		}
	);
	return readApiResponse<MessageRecord>(response, 'message record');
}

export async function fetchMessageFacets(
	sourceName: string,
	document: MessageFilterDocument,
	facetPath: (string | number)[],
	signal: AbortSignal
): Promise<FacetsPayload> {
	const response: Response = await authenticatedFetch(
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
