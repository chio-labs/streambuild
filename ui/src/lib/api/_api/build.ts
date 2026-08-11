import { readApiResponse } from '$lib/api/_api/read-response';
import type { BuildFeed, BuildStartResult, RunEventFeed } from '$lib/api/types';

export async function requestBuildStart(
	selectors: string[],
	startTime: string | null,
	confirmations: string[]
): Promise<BuildStartResult> {
	const response: Response = await fetch('/api/build', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ selectors, startTime, confirmations })
	});
	return readApiResponse<BuildStartResult>(response, 'build start');
}

export async function requestBuildFeed(after: number): Promise<BuildFeed> {
	const response: Response = await fetch(`/api/build/current?after=${after}`);
	return readApiResponse<BuildFeed>(response, 'build feed');
}

export async function requestRunEvents(
	invocationId: string,
	after: number
): Promise<RunEventFeed> {
	const response: Response = await fetch(
		`/api/runs/${encodeURIComponent(invocationId)}/events?after=${after}`
	);
	return readApiResponse<RunEventFeed>(response, 'run events');
}
