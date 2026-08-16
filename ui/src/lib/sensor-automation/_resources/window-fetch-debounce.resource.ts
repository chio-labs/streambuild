// Owns the debounce timer between window interactions and warehouse fetches.

export type WindowFetchDebounce = {
	schedule: (run: () => void) => void;
	cancel: () => void;
};

export function createWindowFetchDebounce(delayMs: number): WindowFetchDebounce {
	let timer: ReturnType<typeof setTimeout> | null = null;

	function cancel(): void {
		if (timer !== null) clearTimeout(timer);
		timer = null;
	}

	function schedule(run: () => void): void {
		cancel();
		timer = setTimeout(() => {
			timer = null;
			run();
		}, delayMs);
	}

	return { schedule, cancel };
}
