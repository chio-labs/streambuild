// Navigation waits for the first inventory fetch: the previous page stays on
// screen until the table can render fully, instead of switching and popping.
// Revisits resolve instantly from the session cache and revalidate in place.
import { topicsStore } from './state.svelte';

export async function load(): Promise<void> {
	await topicsStore.ensureLoaded();
}
