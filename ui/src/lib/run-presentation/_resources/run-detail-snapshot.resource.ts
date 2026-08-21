import { fetchBuildFeed } from '$lib/api/main/build/fetch-build-feed';
import { fetchRunEvents } from '$lib/api/main/build/fetch-run-events';
import { fetchRuns } from '$lib/api/main/runs/fetch-runs';
import type { BuildFeed, RunEventFeed, RunRecord } from '$lib/api/types';
import { RUN_SNAPSHOT_MAX_AGE_MS } from '$lib/run-presentation/constants';
import type {
	RunDetailSnapshot,
	RunDetailSnapshotResource
} from '$lib/run-presentation/types';

export function createRunDetailSnapshotResource(): RunDetailSnapshotResource {
	const snapshots: Map<string, Promise<RunDetailSnapshot>> = new Map();
	const timers: Map<string, ReturnType<typeof setTimeout>> = new Map();

	function remove(invocationId: string, request: Promise<RunDetailSnapshot>): void {
		if (snapshots.get(invocationId) !== request) return;
		snapshots.delete(invocationId);
		const timer: ReturnType<typeof setTimeout> | undefined = timers.get(invocationId);
		if (timer !== undefined) clearTimeout(timer);
		timers.delete(invocationId);
	}

	function prefetch(invocationId: string): Promise<RunDetailSnapshot> {
		const existing: Promise<RunDetailSnapshot> | undefined = snapshots.get(invocationId);
		if (existing !== undefined) return existing;
		const request: Promise<RunDetailSnapshot> = fetchBuildFeed(0).then(
			async (ownership: BuildFeed): Promise<RunDetailSnapshot> => {
				const locallyOwned: boolean =
					ownership.invocationId === invocationId ||
					ownership.currentInvocationId === invocationId;
				if (locallyOwned && ownership.running) {
					return {
						feed: {
							found: false,
							events: [],
							hasMore: false,
							status: null,
							lastSignalAt: null,
							lastSignalAgeSeconds: null,
							statementProgress: null
						},
						ownership,
						record: null
					};
				}
				const [feed, runs]: [RunEventFeed, RunRecord[]] = await Promise.all([
					fetchRunEvents(invocationId, 0),
					fetchRuns()
				]);
				return {
					feed,
					ownership,
					record: runs.find((run: RunRecord) => run.invocationId === invocationId) ?? null
				};
			}
		);
		snapshots.set(invocationId, request);
		const timer: ReturnType<typeof setTimeout> = setTimeout(
			() => remove(invocationId, request),
			RUN_SNAPSHOT_MAX_AGE_MS
		);
		timers.set(invocationId, timer);
		void request.catch(() => remove(invocationId, request));
		return request;
	}

	function consume(invocationId: string): Promise<RunDetailSnapshot> {
		const request: Promise<RunDetailSnapshot> = prefetch(invocationId);
		remove(invocationId, request);
		return request;
	}

	function stop(): void {
		for (const timer of timers.values()) clearTimeout(timer);
		timers.clear();
		snapshots.clear();
	}

	return { prefetch, consume, stop };
}
