// Navigation waits for the first inventory fetch: the previous page stays on
// screen until the table can render fully, instead of switching and popping.
// Revisits resolve instantly from the session cache and revalidate in place.
import { createTopicBrowserState } from '$lib/topic-browser/main/create-topic-browser-state.svelte';

const topicsStore = createTopicBrowserState();

export async function load(): Promise<void> {
	await topicsStore.ensureLoaded();
}
