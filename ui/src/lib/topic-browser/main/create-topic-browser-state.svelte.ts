import { createTopicBrowserState as createState } from '$lib/topic-browser/_state/topic-browser.state.svelte';
import type { TopicBrowserState } from '$lib/topic-browser/types';

export function createTopicBrowserState(): TopicBrowserState {
	return createState();
}
