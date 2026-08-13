import { readApiResponse } from '$lib/api/main/response/read-api-response';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

import type { DeadLetterActionResult, DeadLettersPayload } from '../types';

export async function fetchDeadLetters(signal?: AbortSignal): Promise<DeadLettersPayload> {
	const response: Response = await fetch('/api/sensors/dead-letters', { signal });
	return readApiResponse<DeadLettersPayload>(response, 'sensor dead letters');
}

export async function requestDeadLetterRetry(
	sensorName: string,
	eventId: string
): Promise<DeadLetterActionResult> {
	const response: Response = await authenticatedFetch('/api/sensors/dead-letters/retry', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ sensorName, eventId })
	});
	return readApiResponse<DeadLetterActionResult>(response, 'dead letter retry');
}

export async function requestDeadLetterSkip(
	sensorName: string,
	eventId: string,
	reason: string
): Promise<DeadLetterActionResult> {
	const response: Response = await authenticatedFetch('/api/sensors/dead-letters/skip', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ sensorName, eventId, reason })
	});
	return readApiResponse<DeadLetterActionResult>(response, 'dead letter skip');
}
