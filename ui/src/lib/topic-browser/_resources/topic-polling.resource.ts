import type { TopicPollingResource } from '$lib/topic-browser/types';

const RETRY_DELAY_MS: number = 2_000;

export function createTopicPollingResource(poll: () => Promise<boolean>): TopicPollingResource {
	let timer: ReturnType<typeof setTimeout> | null = null;
	let active: boolean = false;

	async function run(): Promise<void> {
		const pending: boolean = await poll();
		if (active && pending) timer = setTimeout(() => void run(), RETRY_DELAY_MS);
	}

	function stop(): void {
		active = false;
		if (timer !== null) clearTimeout(timer);
		timer = null;
	}

	function start(): () => void {
		if (!active) {
			active = true;
			void run();
		}
		return stop;
	}

	return { start, stop };
}
