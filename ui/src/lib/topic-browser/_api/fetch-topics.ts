import { readApiResponse } from '$lib/api/main/response/read-api-response';
import type { TopicsPayload } from '$lib/topic-browser/types';

export async function fetchTopics(signal: AbortSignal): Promise<TopicsPayload> {
	const response: Response = await fetch('/api/topics', { signal });
	return readApiResponse<TopicsPayload>(response, 'topics request');
}
