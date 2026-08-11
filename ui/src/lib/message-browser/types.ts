export type MessageModeKind = 'newest' | 'timeRange' | 'offsetRange';

export type MessageMode = {
	kind: MessageModeKind;
	fromTime?: string | null;
	toTime?: string | null;
	partition?: number | null;
	fromOffset?: number | null;
	toOffset?: number | null;
};

export type PredicateField = 'partition' | 'key' | 'value' | 'json' | 'header';

export type MessagePredicate = {
	field: PredicateField;
	op: string;
	value?: string | number;
	values?: number[];
	path?: (string | number)[];
};

export type MessageCursor = {
	landedAt: string;
	partition: number;
	offset: number;
};

export type MessageFilterDocument = {
	mode: MessageMode;
	predicates: MessagePredicate[];
	limit: number;
	timeColumn: 'landed' | 'kafka';
	previewPaths: (string | number)[][];
};

export type MessageRow = {
	landedAt: string;
	kafkaTimestamp: string | null;
	partition: number;
	offset: number;
	key: string;
	keyBytes: number;
	valuePreview: string;
	valueBytes: number;
	valueTruncated: boolean;
	headers: [string, string][];
	previewValues: string[];
};

export type MessagesPayload = {
	rows: MessageRow[];
	nextCursor: MessageCursor | null;
	windowSeconds: number | null;
	limit: number;
};

export type MessageRecord = {
	landedAt: string;
	kafkaTimestamp: string | null;
	partition: number;
	offset: number;
	topic: string;
	key: string;
	keyBytes: number;
	value: string;
	valueBytes: number;
	valueTruncated: boolean;
	headers: [string, string][];
};

export type FacetValue = { value: string; count: number };

export type FacetsPayload = {
	values: FacetValue[];
	nullCount: number;
	otherCount: number;
	totalCount: number;
	windowSeconds: number | null;
};

export type MessageBrowserState = {
	readonly document: MessageFilterDocument;
	readonly rows: MessageRow[];
	readonly nextCursor: MessageCursor | null;
	readonly windowSeconds: number | null;
	readonly facets: FacetsPayload | null;
	readonly facetPath: (string | number)[];
	readonly loading: boolean;
	readonly loadingOlder: boolean;
	readonly error: string | null;
	setDocument(document: MessageFilterDocument): void;
	setFacetPath(path: (string | number)[]): void;
	refresh(source?: 'auto' | 'manual'): Promise<void>;
	loadOlder(): Promise<void>;
	stop(): void;
	ensureLoaded(): Promise<void>;
};

export type CopyFeedbackResource = {
	schedule(): void;
	stop(): void;
};

export type HighlightSegment = { text: string; hit: boolean };
