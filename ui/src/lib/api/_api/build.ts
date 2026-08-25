import { readApiResponse } from '$lib/api/_api/read-response';
import type { BuildFeed, BuildStartResult, RunEventFeed } from '$lib/api/types';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestBuildStart(
	selectors: string[],
	startTime: string | null,
	confirmations: string[],
	deploymentId: string | null = null,
	changed: boolean = false,
	includeMissingUpstream: boolean = false
): Promise<BuildStartResult> {
	const response: Response = await authenticatedFetch('/api/build', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({
			selectors,
			...(changed ? { changed: true } : {}),
			...(includeMissingUpstream ? { includeMissingUpstream: true } : {}),
			startTime,
			...(deploymentId === null ? {} : { deploymentId }),
			confirmations
		})
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
