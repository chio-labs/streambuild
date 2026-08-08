import { readApiResponse } from '$lib/api';
import type { TopicsPayload } from './types';

/** Broker topic inventory merged with managed-source lag and retained stats. */
export async function fetchTopics(signal: AbortSignal): Promise<TopicsPayload> {
	const response = await fetch('/api/topics', { signal });
	return readApiResponse<TopicsPayload>(response, 'topics request');
}
