import { prefetchRuns } from '$lib/api/main/runs/prefetch-runs';
import type { RunRecord } from '$lib/api/types';

export async function fetchRuns(): Promise<RunRecord[]> {
	return prefetchRuns();
}
