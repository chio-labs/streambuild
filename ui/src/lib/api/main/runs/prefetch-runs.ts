import { requestRuns } from '$lib/api/_api/runs';
import type { RunRecord } from '$lib/api/types';

const RUNS_PREFETCH_MAX_AGE_MS: number = 10_000;
let runsPrefetch: Promise<RunRecord[]> | null = null;
let runsPrefetchedAt: number = 0;

export function prefetchRuns(): Promise<RunRecord[]> {
	if (runsPrefetch !== null && Date.now() - runsPrefetchedAt < RUNS_PREFETCH_MAX_AGE_MS) {
		return runsPrefetch;
	}
	runsPrefetchedAt = Date.now();
	const request: Promise<RunRecord[]> = requestRuns();
	runsPrefetch = request;
	void request.catch(() => {
		if (runsPrefetch === request) runsPrefetch = null;
	});
	return request;
}
