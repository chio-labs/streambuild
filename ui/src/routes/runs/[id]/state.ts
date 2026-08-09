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
	const request = fetchBuildFeed(0).then(async (ownership) => {
		const locallyOwned =
			ownership.invocationId === invocationId || ownership.currentInvocationId === invocationId;
		if (locallyOwned && ownership.running) {
			return {
				feed: {
					found: false,
					events: [],
					hasMore: false,
					status: null,
					lastSignalAt: null,
					lastSignalAgeSeconds: null
				},
				ownership,
				record: null
			};
		}
		const [feed, runs] = await Promise.all([fetchRunEvents(invocationId, 0), fetchRuns()]);
		return {
			feed,
			ownership,
			record: runs.find((run) => run.invocationId === invocationId) ?? null
		};
	});
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
