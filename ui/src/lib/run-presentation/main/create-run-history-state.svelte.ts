import { fetchRuns } from '$lib/api/main/runs/fetch-runs';
import type { RunRecord } from '$lib/api/types';
import type { RunHistoryState } from '$lib/run-presentation/types';

let cachedRuns: RunRecord[] | null = null;
let cachedAt: number | null = null;

export function createRunHistoryState(): RunHistoryState {
	let runs = $state<RunRecord[] | null>(cachedRuns);
	let error = $state<string | null>(null);
	let refreshing = $state<boolean>(false);
	let updatedAt = $state<number | null>(cachedAt);
	let controller: AbortController | null = null;
	let active: boolean = false;

	async function refresh(): Promise<void> {
		if (refreshing) return;
		controller = new AbortController();
		refreshing = true;
		try {
			const next: RunRecord[] = await fetchRuns(controller.signal);
			if (!active) return;
			runs = next;
			cachedRuns = next;
			updatedAt = Date.now();
			cachedAt = updatedAt;
			error = null;
		} catch (caught) {
			if (active && !(controller?.signal.aborted ?? false)) {
				error = caught instanceof Error ? caught.message : String(caught);
			}
		} finally {
			refreshing = false;
		}
	}

	function start(): () => void {
		active = true;
		void refresh();
		return () => {
			active = false;
			controller?.abort();
		};
	}

	return {
		get runs() {
			return runs;
		},
		get error() {
			return error;
		},
		get refreshing() {
			return refreshing;
		},
		get updatedAt() {
			return updatedAt;
		},
		start,
		refresh
	};
}
