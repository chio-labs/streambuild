import type { CopyFeedbackResource } from '$lib/message-browser/types';

const FEEDBACK_DURATION_MS: number = 1_200;

export function createCopyFeedbackResource(reset: () => void): CopyFeedbackResource {
	let timer: ReturnType<typeof setTimeout> | null = null;

	function stop(): void {
		if (timer !== null) clearTimeout(timer);
		timer = null;
	}

	function schedule(): void {
		stop();
		timer = setTimeout(reset, FEEDBACK_DURATION_MS);
	}

	return { schedule, stop };
}
