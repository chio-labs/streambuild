import { createMessageBrowserState as createState } from '$lib/message-browser/_state/message-browser.state.svelte';
import type { MessageBrowserState } from '$lib/message-browser/types';

export function createMessageBrowserState(sourceName: string): MessageBrowserState {
	return createState(sourceName);
}
