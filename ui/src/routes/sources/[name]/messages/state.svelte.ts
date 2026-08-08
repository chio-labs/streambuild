import { fetchMessageFacets, fetchMessages } from './api';
import type {
	FacetsPayload,
	MessageCursor,
	MessageFilterDocument,
	MessagePredicate,
	MessageRow,
	MessagesPayload
} from './types';

export const DEFAULT_LIMIT = 50;
export const DEFAULT_FACET_PATH: (string | number)[] = ['message_type'];

export function defaultFilterDocument(): MessageFilterDocument {
	return {
		mode: { kind: 'newest' },
		predicates: [],
		limit: DEFAULT_LIMIT,
		timeColumn: 'landed',
		previewPaths: []
	};
}

/** Serialize the filter document into a shareable query string value. */
export function encodeFilterDocument(document: MessageFilterDocument): string | null {
	const isDefault =
		document.mode.kind === 'newest' &&
		document.predicates.length === 0 &&
		document.limit === DEFAULT_LIMIT &&
		document.timeColumn === 'landed' &&
		document.previewPaths.length === 0;
	return isDefault ? null : JSON.stringify(document);
}

/** Parse a shared query string value back into a filter document, tolerating junk. */
export function decodeFilterDocument(encoded: string | null): MessageFilterDocument {
	if (!encoded) return defaultFilterDocument();
	try {
		const parsed = JSON.parse(encoded) as Partial<MessageFilterDocument>;
		return {
			mode: parsed.mode ?? { kind: 'newest' },
			predicates: Array.isArray(parsed.predicates) ? parsed.predicates : [],
			limit: typeof parsed.limit === 'number' ? parsed.limit : DEFAULT_LIMIT,
			timeColumn: parsed.timeColumn === 'kafka' ? 'kafka' : 'landed',
			previewPaths: Array.isArray(parsed.previewPaths) ? parsed.previewPaths : []
		};
	} catch {
		return defaultFilterDocument();
	}
}

/** Whether a document is complete enough to query; half-built modes never fire. */
export function isQueryableDocument(document: MessageFilterDocument): boolean {
	if (document.mode.kind === 'timeRange') {
		return Boolean(document.mode.fromTime) || Boolean(document.mode.toTime);
	}
	if (document.mode.kind === 'offsetRange') {
		return document.mode.partition !== null && document.mode.partition !== undefined;
	}
	return true;
}

/** One human-readable label per chip, mirroring the server-side SQL semantics. */
export function predicateLabel(predicate: MessagePredicate): string {
	if (predicate.field === 'partition') return `partition in [${(predicate.values ?? []).join(', ')}]`;
	if (predicate.field === 'json') {
		const path = (predicate.path ?? []).join('.');
		if (predicate.op === 'exists') return `json ${path} exists`;
		return `json ${path} ${predicate.op} ${String(predicate.value ?? '')}`;
	}
	return `${predicate.field} ${predicate.op} ${String(predicate.value ?? '')}`;
}

export function createMessageBrowserState(sourceName: string) {
	let document = $state<MessageFilterDocument>(defaultFilterDocument());
	let rows = $state<MessageRow[]>([]);
	let nextCursor = $state<MessageCursor | null>(null);
	let windowSeconds = $state<number | null>(null);
	let facets = $state<FacetsPayload | null>(null);
	let facetPath = $state<(string | number)[]>(DEFAULT_FACET_PATH);
	let loading = $state(false);
	let loadingOlder = $state(false);
	let error = $state<string | null>(null);
	let generation = 0;
	let controller: AbortController | null = null;

	async function refresh(): Promise<void> {
		const snapshot = $state.snapshot(document) as MessageFilterDocument;
		if (!isQueryableDocument(snapshot)) return;
		controller?.abort();
		generation += 1;
		const current = generation;
		controller = new AbortController();
		loading = true;
		error = null;
		try {
			const [messages, facetsPayload] = await Promise.all([
				fetchMessages(sourceName, snapshot, null, controller.signal),
				fetchMessageFacets(
					sourceName,
					snapshot,
					$state.snapshot(facetPath) as (string | number)[],
					controller.signal
				).catch(() => null)
			]);
			if (current !== generation) return;
			rows = messages.rows;
			nextCursor = messages.nextCursor;
			windowSeconds = messages.windowSeconds;
			facets = facetsPayload;
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
		const current = generation;
		loadingOlder = true;
		try {
			const older: MessagesPayload = await fetchMessages(
				sourceName,
				$state.snapshot(document) as MessageFilterDocument,
				$state.snapshot(nextCursor) as MessageCursor,
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

	function stop(): void {
		generation += 1;
		controller?.abort();
	}

	return {
		get document() {
			return document;
		},
		set document(next: MessageFilterDocument) {
			document = next;
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
		set facetPath(next: (string | number)[]) {
			facetPath = next;
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
		refresh,
		loadOlder,
		stop
	};
}
