import { fetchTopics } from '$lib/topic-browser/_api/fetch-topics';
import { createTopicPollingResource } from '$lib/topic-browser/_resources/topic-polling.resource';
import type {
	TopicBrowserState,
	TopicPollingResource,
	TopicsPayload
} from '$lib/topic-browser/types';

let cachedPayload: TopicsPayload | null = null;
let cachedAt: number | null = null;

export function createTopicBrowserState(): TopicBrowserState {
	let payload = $state<TopicsPayload | null>(cachedPayload);
	let error = $state<string | null>(null);
	let loading = $state<boolean>(false);
	let updatedAt = $state<number | null>(cachedAt);
	let generation: number = 0;
	let controller: AbortController | null = null;

	async function refresh(): Promise<boolean> {
		controller?.abort();
		generation += 1;
		const current: number = generation;
		controller = new AbortController();
		loading = true;
		try {
			const next: TopicsPayload = await fetchTopics(controller.signal);
			if (current !== generation) return false;
			payload = next;
			cachedPayload = next;
			updatedAt = Date.now();
			cachedAt = updatedAt;
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

	const polling: TopicPollingResource = createTopicPollingResource(refresh);

	function stop(): void {
		polling.stop();
		generation += 1;
		controller?.abort();
	}

	function start(): () => void {
		polling.start();
		return stop;
	}

	async function ensureLoaded(): Promise<void> {
		if (payload !== null) return;
		await refresh();
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
		get updatedAt() {
			return updatedAt;
		},
		refresh,
		start,
		stop,
		ensureLoaded
	};
}
