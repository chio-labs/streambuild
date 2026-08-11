import { goto } from '$app/navigation';
import { prefetchRuns } from '$lib/api/main/runs/prefetch-runs';

export async function navigateToRuns(event: MouseEvent): Promise<void> {
	if (
		event.button !== 0 ||
		event.metaKey ||
		event.ctrlKey ||
		event.shiftKey ||
		event.altKey
	) {
		return;
	}
	event.preventDefault();
	try {
		await prefetchRuns();
	} catch {
		// Navigation still exposes the page's ordinary retry and error state.
	}
	await goto('/runs');
}
