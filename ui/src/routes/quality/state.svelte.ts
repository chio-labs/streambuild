import { fetchAuditScheduler } from './api';
import type { AuditSchedulerPayload } from './types';

const REFRESH_INTERVAL_MS = 10_000;

export function createAuditSchedulerState() {
	let payload = $state<AuditSchedulerPayload | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let refreshing = false;
	let generation = 0;
	let controller: AbortController | null = null;

	async function refresh(): Promise<void> {
		if (refreshing) return;
		refreshing = true;
		const currentGeneration = generation;
		controller = new AbortController();
		try {
			const nextPayload = await fetchAuditScheduler(controller.signal);
			if (currentGeneration === generation) {
				payload = nextPayload;
				error = null;
			}
		} catch (caught) {
			if (currentGeneration === generation && !controller.signal.aborted) {
				error = String(caught);
			}
		} finally {
			if (currentGeneration === generation) loading = false;
			refreshing = false;
			controller = null;
		}
	}

	function start(): () => void {
		void refresh();
		const timer = setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
		return () => {
			clearInterval(timer);
			generation += 1;
			controller?.abort();
		};
	}

	return {
		get payload() {
			return payload;
		},
		get error() {
			return error;
		},
		get loading() {
			return loading;
		},
		start
	};
}
