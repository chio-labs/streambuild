import { readApiResponse } from '$lib/api/_api/read-response';
import type { CheckRunResult, CheckStatusRecord } from '$lib/api/types';
import { authenticatedFetch } from '$lib/auth/main/authenticated-fetch';

export async function requestCheckStatuses(): Promise<CheckStatusRecord[]> {
	const response: Response = await fetch('/api/checks/status');
	return readApiResponse<CheckStatusRecord[]>(response, 'checks status request');
}

export async function requestCheckRun(
	kind: 'audit' | 'test',
	name: string
): Promise<CheckRunResult> {
	const response: Response = await authenticatedFetch('/api/checks/run', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ kind, name })
	});
	return readApiResponse<CheckRunResult>(response, 'check run');
}
