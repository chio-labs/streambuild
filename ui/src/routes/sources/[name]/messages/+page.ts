// Navigation waits for the first message query: click, the data loads, then
// the page switches fully rendered. Revisits with an unchanged filter
// signature resolve instantly from the per-source session state.
import type { PageLoad } from './$types';
import { createMessageBrowserState } from '$lib/message-browser/main/create-message-browser-state.svelte';
import { decodeFilterDocument } from '$lib/message-browser/main/decode-filter-document';
import type { MessageBrowserState } from '$lib/message-browser/types';

export const load: PageLoad = async ({ params, url }) => {
	const browser: MessageBrowserState = createMessageBrowserState(params.name);
	browser.setDocument(decodeFilterDocument(url.searchParams.get('q')));
	await browser.ensureLoaded();
};
