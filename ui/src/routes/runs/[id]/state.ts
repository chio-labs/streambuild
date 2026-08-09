import { fetchBuildFeed, fetchRunEvents, fetchRuns } from '$lib/api';
import type { BuildFeed, RunEventFeed, RunRecord } from '$lib/api';

export type RunDetailSnapshot = {
	feed: RunEventFeed;
	ownership: BuildFeed;
	record: RunRecord | null;
};

const snapshots = new Map<string, Promise<RunDetailSnapshot>>();
const SNAPSHOT_MAX_AGE_MS = 10_000;

/** Share one initial snapshot between route preloading and the mounted page. */
export function prefetchRunDetail(invocationId: string): Promise<RunDetailSnapshot> {
	const existing = snapshots.get(invocationId);
	if (existing !== undefined) return existing;
	const request = Promise.all([
		fetchRunEvents(invocationId, 0),
		fetchBuildFeed(0),
		fetchRuns()
	]).then(([feed, ownership, runs]) => ({
		feed,
		ownership,
		record: runs.find((run) => run.invocationId === invocationId) ?? null
	}));
	snapshots.set(invocationId, request);
	setTimeout(() => {
		if (snapshots.get(invocationId) === request) snapshots.delete(invocationId);
	}, SNAPSHOT_MAX_AGE_MS);
	void request.catch(() => {
		if (snapshots.get(invocationId) === request) snapshots.delete(invocationId);
	});
	return request;
}

export function consumeRunDetail(invocationId: string): Promise<RunDetailSnapshot> {
	const request = prefetchRunDetail(invocationId);
	snapshots.delete(invocationId);
	return request;
}
