import { readApiResponse } from '$lib/api/_api/read-response';
import type { RunRecord } from '$lib/api/types';

export async function requestRuns(): Promise<RunRecord[]> {
	const response: Response = await fetch('/api/runs');
	return readApiResponse<RunRecord[]>(response, 'runs request');
}
