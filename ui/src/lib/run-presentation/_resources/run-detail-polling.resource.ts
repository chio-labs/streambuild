import type { RunDetailPollingResource } from '$lib/run-presentation/types';

export function createRunDetailPollingResource(
	poll: () => Promise<void>
): RunDetailPollingResource {
	let timer: ReturnType<typeof setTimeout> | null = null;

	return {
		schedule(delayMs: number): void {
			if (timer !== null) clearTimeout(timer);
			timer = setTimeout(() => {
				timer = null;
				void poll();
			}, delayMs);
		},
		stop(): void {
			if (timer !== null) clearTimeout(timer);
			timer = null;
		}
	};
}
