import {
	DEFAULT_MESSAGE_FACET_PATH,
	DEFAULT_MESSAGE_LIMIT
} from '$lib/message-browser/constants';
import type {
	MessageFilterDocument,
	MessageMode,
	MessageModeKind,
	MessagePredicate,
	PredicateField
} from '$lib/message-browser/types';

type JsonRecord = Record<string, unknown>;

export function defaultFilterDocument(): MessageFilterDocument {
	return {
		mode: { kind: 'newest' },
		predicates: [],
		limit: DEFAULT_MESSAGE_LIMIT,
		timeColumn: 'landed',
		previewPaths: []
	};
}

export function encodeFilterDocument(document: MessageFilterDocument): string | null {
	const isDefault: boolean =
		document.mode.kind === 'newest' &&
		document.predicates.length === 0 &&
		document.limit === DEFAULT_MESSAGE_LIMIT &&
		document.timeColumn === 'landed' &&
		document.previewPaths.length === 0;
	return isDefault ? null : JSON.stringify(document);
}

export function decodeFilterDocument(encoded: string | null): MessageFilterDocument {
	if (!encoded) return defaultFilterDocument();
	try {
		const parsed: unknown = JSON.parse(encoded);
		if (!matchesRecord(parsed)) return defaultFilterDocument();
		return {
			mode: matchesMessageMode(parsed.mode) ? parsed.mode : { kind: 'newest' },
			predicates: Array.isArray(parsed.predicates)
				? parsed.predicates.filter(matchesMessagePredicate)
				: [],
			limit: typeof parsed.limit === 'number' ? parsed.limit : DEFAULT_MESSAGE_LIMIT,
			timeColumn: parsed.timeColumn === 'kafka' ? 'kafka' : 'landed',
			previewPaths: Array.isArray(parsed.previewPaths)
				? parsed.previewPaths.filter(matchesMessagePath)
				: []
		};
	} catch {
		return defaultFilterDocument();
	}
}

export function isQueryableDocument(document: MessageFilterDocument): boolean {
	if (document.mode.kind === 'timeRange') {
		return Boolean(document.mode.fromTime) || Boolean(document.mode.toTime);
	}
	if (document.mode.kind === 'offsetRange') {
		return document.mode.partition !== null && document.mode.partition !== undefined;
	}
	return true;
}

export function predicateLabel(predicate: MessagePredicate): string {
	if (predicate.field === 'partition') return `partition in [${(predicate.values ?? []).join(', ')}]`;
	if (predicate.field === 'json') {
		const path: string = (predicate.path ?? []).join('.');
		if (predicate.op === 'exists') return `json ${path} exists`;
		return `json ${path} ${predicate.op} ${String(predicate.value ?? '')}`;
	}
	return `${predicate.field} ${predicate.op} ${String(predicate.value ?? '')}`;
}

export function defaultFacetPath(): (string | number)[] {
	return [...DEFAULT_MESSAGE_FACET_PATH];
}

function matchesRecord(value: unknown): value is JsonRecord {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function matchesMessageMode(value: unknown): value is MessageMode {
	if (!matchesRecord(value) || !matchesMessageModeKind(value.kind)) return false;
	return optionalString(value.fromTime) && optionalString(value.toTime) && optionalNumber(value.partition) && optionalNumber(value.fromOffset) && optionalNumber(value.toOffset);
}

function matchesMessageModeKind(value: unknown): value is MessageModeKind {
	return value === 'newest' || value === 'timeRange' || value === 'offsetRange';
}

function matchesMessagePredicate(value: unknown): value is MessagePredicate {
	return matchesRecord(value) && matchesPredicateField(value.field) && typeof value.op === 'string';
}

function matchesPredicateField(value: unknown): value is PredicateField {
	return value === 'partition' || value === 'key' || value === 'value' || value === 'json' || value === 'header';
}

function matchesMessagePath(value: unknown): value is (string | number)[] {
	return Array.isArray(value) && value.every((segment) => typeof segment === 'string' || typeof segment === 'number');
}

function optionalString(value: unknown): boolean {
	return value === undefined || value === null || typeof value === 'string';
}

function optionalNumber(value: unknown): boolean {
	return value === undefined || value === null || typeof value === 'number';
}
