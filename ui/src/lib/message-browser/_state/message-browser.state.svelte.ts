import {
	fetchMessageFacets,
	fetchMessages
} from '$lib/message-browser/_api/message-requests';
import {
	defaultFacetPath,
	defaultFilterDocument,
	isQueryableDocument
} from '$lib/message-browser/_helpers/filter-document';
import type {
	FacetsPayload,
	MessageBrowserState,
	MessageCursor,
	MessageFilterDocument,
	MessageRow,
	MessagesPayload
} from '$lib/message-browser/types';

const statesBySource: Map<string, MessageBrowserState> = new Map<string, MessageBrowserState>();

export function createMessageBrowserState(sourceName: string): MessageBrowserState {
	const existing: MessageBrowserState | undefined = statesBySource.get(sourceName);
	if (existing !== undefined) return existing;

	let document = $state<MessageFilterDocument>(defaultFilterDocument());
	let rows = $state<MessageRow[]>([]);
	let nextCursor = $state<MessageCursor | null>(null);
	let windowSeconds = $state<number | null>(null);
	let facets = $state<FacetsPayload | null>(null);
	let facetPath = $state<(string | number)[]>(defaultFacetPath());
	let loading = $state<boolean>(false);
	let loadingOlder = $state<boolean>(false);
	let error = $state<string | null>(null);
	let generation: number = 0;
	let controller: AbortController | null = null;
	let searchedSignature: string | null = null;

	async function refresh(source: 'auto' | 'manual' = 'auto'): Promise<void> {
		const snapshot: MessageFilterDocument = $state.snapshot(document);
		if (!isQueryableDocument(snapshot)) return;
		const facetPathSnapshot: (string | number)[] = $state.snapshot(facetPath);
		const signature: string = JSON.stringify({ snapshot, facetPath: facetPathSnapshot });
		if (source === 'auto' && signature === searchedSignature) return;
		controller?.abort();
		generation += 1;
		const current: number = generation;
		controller = new AbortController();
		loading = true;
		error = null;
		try {
			const result: [MessagesPayload, FacetsPayload | null] = await Promise.all([
				fetchMessages(sourceName, snapshot, null, controller.signal),
				fetchMessageFacets(sourceName, snapshot, facetPathSnapshot, controller.signal).catch(
					() => null
				)
			]);
			if (current !== generation) return;
			const [messages, facetsPayload]: [MessagesPayload, FacetsPayload | null] = result;
			rows = messages.rows;
			nextCursor = messages.nextCursor;
			windowSeconds = messages.windowSeconds;
			facets = facetsPayload;
			searchedSignature = signature;
		} catch (caught) {
			if (current === generation && !(controller?.signal.aborted ?? false)) {
				error = String(caught instanceof Error ? caught.message : caught);
				rows = [];
				nextCursor = null;
				facets = null;
			}
		} finally {
			if (current === generation) loading = false;
		}
	}

	async function loadOlder(): Promise<void> {
		if (nextCursor === null || loadingOlder) return;
		const current: number = generation;
		loadingOlder = true;
		try {
			const older: MessagesPayload = await fetchMessages(
				sourceName,
				$state.snapshot(document),
				$state.snapshot(nextCursor),
				new AbortController().signal
			);
			if (current !== generation) return;
			rows = [...rows, ...older.rows];
			nextCursor = older.nextCursor;
		} catch (caught) {
			if (current === generation) {
				error = String(caught instanceof Error ? caught.message : caught);
			}
		} finally {
			loadingOlder = false;
		}
	}

	function setDocument(next: MessageFilterDocument): void {
		document = next;
	}

	function setFacetPath(next: (string | number)[]): void {
		facetPath = next;
	}

	function stop(): void {
		generation += 1;
		controller?.abort();
	}

	async function ensureLoaded(): Promise<void> {
		await refresh('auto');
	}

	const state: MessageBrowserState = {
		get document() {
			return document;
		},
		get rows() {
			return rows;
		},
		get nextCursor() {
			return nextCursor;
		},
		get windowSeconds() {
			return windowSeconds;
		},
		get facets() {
			return facets;
		},
		get facetPath() {
			return facetPath;
		},
		get loading() {
			return loading;
		},
		get loadingOlder() {
			return loadingOlder;
		},
		get error() {
			return error;
		},
		setDocument,
		setFacetPath,
		refresh,
		loadOlder,
		stop,
		ensureLoaded
	};
	statesBySource.set(sourceName, state);
	return state;
}
