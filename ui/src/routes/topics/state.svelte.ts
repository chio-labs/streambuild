import { fetchTopics } from './api';
import type { TopicsPayload } from './types';

// Module-level state: the last inventory survives route remounts, so
// returning to the page renders instantly and refreshes in place instead
// of blanking and popping back in.
let payload = $state<TopicsPayload | null>(null);
let error = $state<string | null>(null);
let loading = $state(false);
let generation = 0;
let controller: AbortController | null = null;

async function refresh(): Promise<boolean> {
	controller?.abort();
	generation += 1;
	const current = generation;
	controller = new AbortController();
	loading = true;
	try {
		const next = await fetchTopics(controller.signal);
		if (current !== generation) return false;
		payload = next;
		error = null;
		return next.pendingBrokers.length > 0;
	} catch (caught) {
		if (current === generation && !(controller?.signal.aborted ?? false)) {
			error = String(caught instanceof Error ? caught.message : caught);
		}
		return false;
	} finally {
		if (current === generation) loading = false;
	}
}

function stop(): void {
	generation += 1;
	controller?.abort();
}

export const topicsStore = {
	get payload() {
		return payload;
	},
	get error() {
		return error;
	},
	get loading() {
		return loading;
	},
	refresh,
	stop
};
