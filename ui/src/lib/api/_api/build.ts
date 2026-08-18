import { readApiResponse } from '$lib/api/_api/read-response';
import type { BuildFeed, BuildStartResult, RunEventFeed, RunStatement } from '$lib/api/types';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestBuildStart(
	selectors: string[],
	startTime: string | null,
	confirmations: string[],
	deploymentId: string | null = null
): Promise<BuildStartResult> {
	const response: Response = await authenticatedFetch('/api/build', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({
			selectors,
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

export async function requestRunStatement(
	invocationId: string,
	statementSequence: number
): Promise<RunStatement> {
	const response: Response = await fetch(
		`/api/runs/${encodeURIComponent(invocationId)}/statements/${statementSequence}`
	);
	return readApiResponse<RunStatement>(response, 'run statement');
}
