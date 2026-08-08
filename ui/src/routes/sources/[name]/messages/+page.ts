// Navigation waits for the first message query: click, the data loads, then
// the page switches fully rendered. Revisits with an unchanged filter
// signature resolve instantly from the per-source session state.
import type { PageLoad } from './$types';
import { decodeFilterDocument, getMessageBrowserState } from './state.svelte';

export const load: PageLoad = async ({ params, url }) => {
	const browser = getMessageBrowserState(params.name);
	browser.document = decodeFilterDocument(url.searchParams.get('q'));
	await browser.ensureLoaded();
};
