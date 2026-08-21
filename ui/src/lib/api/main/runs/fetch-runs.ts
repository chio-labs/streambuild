import { requestRuns } from '$lib/api/_api/runs';
import type { RunRecord } from '$lib/api/types';

export async function fetchRuns(signal?: AbortSignal): Promise<RunRecord[]> {
	return requestRuns(signal);
}
