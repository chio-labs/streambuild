import { createRunDetailState } from '$lib/run-presentation/_state/run-detail.state.svelte';
import type { RunDetailController } from '$lib/run-presentation/types';

export function createRunDetail(
	navigateToActiveRun: (invocationId: string) => Promise<void>
): RunDetailController {
	return createRunDetailState(navigateToActiveRun);
}
