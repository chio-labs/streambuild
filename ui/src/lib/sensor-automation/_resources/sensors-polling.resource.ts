import type { SensorsPollingResource } from '../types';

const REFRESH_INTERVAL_MS: number = 10_000;

export function createSensorsPollingResource(
	refresh: () => Promise<void>
): SensorsPollingResource {
	let timer: ReturnType<typeof setInterval> | null = null;

	function stop(): void {
		if (timer === null) return;
		clearInterval(timer);
		timer = null;
	}

	function start(): () => void {
		if (timer === null) {
			void refresh();
			timer = setInterval(() => void refresh(), REFRESH_INTERVAL_MS);
		}
		return stop;
	}

	return { start, stop };
}
