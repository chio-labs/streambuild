import { cancelBuild } from '$lib/api/main/build/cancel-build';
import { fetchBuildFeed } from '$lib/api/main/build/fetch-build-feed';
import { fetchRunEvents } from '$lib/api/main/build/fetch-run-events';
import { killBuild } from '$lib/api/main/build/kill-build';
import { refreshDeployments } from '$lib/api/main/project/refresh-deployments';
import { refreshLiveState } from '$lib/api/main/project/refresh-live-state';
import { fetchRuns } from '$lib/api/main/runs/fetch-runs';
import type { BuildFeed, RunEvent, RunEventFeed, RunRecord } from '$lib/api/types';
import { createRunDetailPollingResource } from '$lib/run-presentation/_resources/run-detail-polling.resource';
import { RUN_DETAIL_POLL_MS } from '$lib/run-presentation/constants';
import { consumeRunDetail } from '$lib/run-presentation/main/_consume-run-detail';
import type {
	RunDetailController,
	RunDetailPollingResource,
	RunDetailSnapshot,
	RunDetailView
} from '$lib/run-presentation/types';

export function createRunDetailState(
	navigateToActiveRun: (invocationId: string) => Promise<void>
): RunDetailController {
	const view: RunDetailView = $state({
		events: [],
		running: true,
		status: 'running',
		exitCode: null,
		stderr: '',
		owned: false,
		ownedRunning: false,
		ownerInvocationId: null,
		forceAvailable: false,
		signalling: false,
		lastSignalAgeSeconds: null,
		statementProgress: null,
		record: null,
		commandLine: 'build',
		loadError: null,
		pollError: null,
		notFound: false,
		initialLoading: true
	});
	let activeGeneration: number = 0;
	let invocationId: string = '';
	let live: boolean = false;
	let cursor: number = 0;
	const polling: RunDetailPollingResource = createRunDetailPollingResource(() =>
		pollDurable(activeGeneration)
	);

	function start(nextInvocationId: string, nextLive: boolean): void {
		stop();
		const generation: number = activeGeneration;
		invocationId = nextInvocationId;
		live = nextLive;
		cursor = 0;
		resetView();
		void consumeRunDetail(invocationId).then(
			(initial: RunDetailSnapshot) => pollDurable(generation, initial),
			() => pollDurable(generation)
		);
	}

	function stop(): void {
		activeGeneration += 1;
		polling.stop();
	}

	function resetView(): void {
		Object.assign(view, {
			events: [],
			running: true,
			status: 'running',
			exitCode: null,
			stderr: '',
			owned: false,
			ownedRunning: false,
			ownerInvocationId: null,
			forceAvailable: false,
			signalling: false,
			lastSignalAgeSeconds: null,
			statementProgress: null,
			record: null,
			commandLine: 'build',
			loadError: null,
			pollError: null,
			notFound: false,
			initialLoading: true
		});
	}

	async function pollDurable(
		generation: number,
		initial?: RunDetailSnapshot
	): Promise<void> {
		try {
			const feed: RunEventFeed = initial?.feed ?? (await fetchRunEvents(invocationId, cursor));
			if (!isActive(generation)) return;
			if (feed.events.length > 0) cursor = feed.events[feed.events.length - 1].sequence;
			const combinedEvents: RunEvent[] = [
				...view.events,
				...feed.events.filter((event: RunEvent) => event.event !== 'run_heartbeat')
			];
			const runStarted: RunEvent | undefined = combinedEvents.find(
				(event: RunEvent) => event.event === 'run_started'
			);
			view.events = combinedEvents;
			view.status = feed.status ?? 'running';
			view.lastSignalAgeSeconds = feed.lastSignalAgeSeconds;
			view.statementProgress = feed.statementProgress;
			view.running = view.status === 'running' || view.status === 'unresponsive';
			const ownership: BuildFeed = initial?.ownership ?? (await fetchBuildFeed(0));
			if (!isActive(generation)) return;
			view.owned =
				ownership.invocationId === invocationId || ownership.currentInvocationId === invocationId;
			view.ownedRunning = view.owned && ownership.running;
			view.ownerInvocationId = view.owned ? ownership.invocationId : null;
			if (view.owned) {
				view.stderr = ownership.stderr;
				view.forceAvailable = ownership.forceAvailable;
			}
			if (
				ownership.running &&
				live &&
				ownership.invocationId === invocationId &&
				ownership.currentInvocationId !== null &&
				ownership.currentInvocationId !== invocationId
			) {
				await navigateToActiveRun(ownership.currentInvocationId);
				return;
			}
			applyOwnershipFallback(feed, ownership);
			const loadedRecord: RunRecord | null =
				initial !== undefined
					? initial.record
					: view.ownedRunning
						? view.record
						: await loadRunRecord(invocationId);
			if (!isActive(generation)) return;
			if (!feed.found && !view.owned && loadedRecord === null) {
				view.notFound = true;
				view.running = false;
				view.loadError = null;
				view.initialLoading = false;
				return;
			}
			view.notFound = false;
			view.record = loadedRecord;
			if (view.record !== null) {
				view.exitCode = view.record.exitCode;
				view.status = feed.status ?? view.record.status;
			}
			view.commandLine =
				runStarted?.displayCommand ??
				(view.owned && ownership.command ? ownership.command : null) ??
				view.record?.displayCommand ??
				view.record?.command ??
				'build';
			view.pollError = null;
			view.loadError = null;
			view.initialLoading = false;
			if (view.running || feed.hasMore) {
				polling.schedule(feed.hasMore ? 0 : RUN_DETAIL_POLL_MS);
			} else {
				void Promise.all([refreshLiveState(), refreshDeployments()]);
			}
		} catch (error) {
			if (!isActive(generation)) return;
			view.pollError = error instanceof Error ? error.message : String(error);
			view.initialLoading = false;
			polling.schedule(RUN_DETAIL_POLL_MS);
		}
	}

	function isActive(generation: number): boolean {
		return generation === activeGeneration;
	}

	function applyOwnershipFallback(feed: RunEventFeed, ownership: BuildFeed): void {
		if (view.owned && !feed.found) {
			view.exitCode = ownership.exitCode;
			view.running = ownership.running;
			view.status = ownership.running
				? 'running'
				: ownership.exitCode === 0
					? 'succeeded'
					: 'failed';
		} else if (view.ownedRunning && !view.running) {
			view.running = true;
			view.status = 'running';
		}
	}

	async function loadRunRecord(id: string): Promise<RunRecord | null> {
		const runs: RunRecord[] = await fetchRuns();
		return runs.find((run: RunRecord) => run.invocationId === id) ?? null;
	}

	async function requestCancel(): Promise<void> {
		if (
			!window.confirm(
				'Cancel this build? Direct mode may leave the selected closure partially rebuilt. Rerunning is safe.'
			)
		)
			return;
		view.signalling = true;
		try {
			const result: Awaited<ReturnType<typeof cancelBuild>> = await cancelBuild(
				view.ownerInvocationId ?? invocationId
			);
			view.forceAvailable = Boolean(result.forceAvailable);
		} catch (error) {
			view.loadError = error instanceof Error ? error.message : String(error);
		} finally {
			view.signalling = false;
		}
	}

	async function requestKill(): Promise<void> {
		view.signalling = true;
		try {
			await killBuild(view.ownerInvocationId ?? invocationId);
			view.forceAvailable = false;
		} catch (error) {
			view.loadError = error instanceof Error ? error.message : String(error);
		} finally {
			view.signalling = false;
		}
	}

	return { view, start, stop, requestCancel, requestKill };
}
