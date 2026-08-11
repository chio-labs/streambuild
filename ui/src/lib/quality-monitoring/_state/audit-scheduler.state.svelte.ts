import { fetchAuditScheduler } from '$lib/quality-monitoring/_api/fetch-audit-scheduler';
import { createAuditSchedulerPollingResource } from '$lib/quality-monitoring/_resources/audit-scheduler-polling.resource';
import type {
	AuditSchedulerPayload,
	AuditSchedulerPollingResource,
	AuditSchedulerState
} from '$lib/quality-monitoring/types';

let cachedPayload: AuditSchedulerPayload | null = null;

export function createAuditSchedulerState(): AuditSchedulerState {
	let payload = $state<AuditSchedulerPayload | null>(cachedPayload);
	let error = $state<string | null>(null);
	let loading = $state<boolean>(cachedPayload === null);
	let refreshing: boolean = false;
	let generation: number = 0;
	let controller: AbortController | null = null;

	async function refresh(): Promise<void> {
		if (refreshing) return;
		refreshing = true;
		const currentGeneration: number = generation;
		controller = new AbortController();
		try {
			const nextPayload: AuditSchedulerPayload = await fetchAuditScheduler(controller.signal);
			if (currentGeneration === generation) {
				payload = nextPayload;
				cachedPayload = nextPayload;
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

	const polling: AuditSchedulerPollingResource = createAuditSchedulerPollingResource(refresh);

	function start(): () => void {
		const stopPolling: () => void = polling.start();
		return () => {
			stopPolling();
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
