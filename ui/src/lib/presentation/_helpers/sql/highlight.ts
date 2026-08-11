// StreamBuild-aware syntax highlighting.
//
// StreamBuild SQL is a superset of ClickHouse SQL with TWO header dialects, which
// is why no stock grammar can render it:
//
//   MODEL (...)   whitespace-separated `key value`, lists [...], nested maps (...),
//                 optional trailing commas. `key: value` and {...} are INVALID.
//   AUDIT (...)   colon form — name: "…", severity: "…", description: "…"
//   TEST  (...)   colon form, plus INPUT / EXPECT / EXPECT ZERO ROWS blocks
//
// Plus `__source()` / `__ref()` references with a `ref_type=` named argument, and
// generic-audit placeholders `@name` / `@'name'`.
//
// Output is class-based (.token.*), themed via CSS variables in layout.css so it
// adapts to light/dark automatically.

import Prism from 'prismjs';
import 'prismjs/components/prism-sql';

let registered = false;

/** MODEL() header fields — StreamBuild's ALLOWED_MODEL_KEYS, and nothing else. */
const MODEL_HEADER_KEYS: string[] = [
	'kind',
	'relation_name',
	'engine',
	'order_by',
	'partition_by',
	'ttl',
	'settings',
	'replay_anchor',
	'replay_on_change',
	'bounded_replay_fallback'
];

/** Block keywords that open a header or a test section. */
const BLOCK_KEYWORDS: string[] = ['MODEL', 'AUDIT', 'TEST', 'INPUT', 'EXPECT', 'ZERO', 'ROWS'];

/** Header field values that read as keywords rather than identifiers. */
const HEADER_VALUES: string[] = ['auto', 'never', 'table', 'view', 'full', 'bounded_without_history'];

/** AUDIT()/TEST() colon-form fields. */
const CHECK_HEADER_KEYS: string[] = ['name', 'severity', 'description'];

/** ClickHouse engines and type constructors worth colouring. */
const CLICKHOUSE_KEYWORDS: string[] = [
	'MergeTree',
	'ReplacingMergeTree',
	'SummingMergeTree',
	'AggregatingMergeTree',
	'CollapsingMergeTree',
	'VersionedCollapsingMergeTree',
	'ReplicatedMergeTree',
	'ReplicatedReplacingMergeTree',
	'Kafka',
	'MaterializedView',
	'AggregateFunction',
	'SimpleAggregateFunction',
	'LowCardinality',
	'Nullable',
	'DateTime64',
	'DateTime',
	'Date32',
	'Date',
	'UInt8',
	'UInt16',
	'UInt32',
	'UInt64',
	'Int8',
	'Int16',
	'Int32',
	'Int64',
	'Float32',
	'Float64',
	'Decimal',
	'String',
	'FixedString',
	'UUID',
	'Array',
	'Tuple',
	'Map',
	'INTERVAL',
	'MATERIALIZED',
	'GRANULARITY'
];

function alternation(words: string[]): string {
	return words.join('|');
}

export function ensureStreambuildGrammar(): void {
	if (registered) return;
	registered = true;

	const streambuild: Prism.Grammar = Prism.languages.extend('sql', {});

	// Reference functions: __source("orders"), __ref("orders", ref_type="reference")
	Prism.languages.insertBefore('streambuild', 'function', {
		'sb-ref': {
			pattern: /\b__(?:source|ref)\b(?=\s*\()/,
			alias: 'function'
		},
		// Generic-audit placeholders: @column, @'values', @macro_name(...)
		'sb-placeholder': {
			pattern: /@'?[A-Za-z_][\w]*'?/,
			alias: 'function'
		}
	});

	Prism.languages.insertBefore('streambuild', 'keyword', {
		// Block openers — MODEL ( / AUDIT ( / TEST ( / EXPECT ZERO ROWS
		'sb-block': {
			pattern: new RegExp(`\\b(?:${alternation(BLOCK_KEYWORDS)})\\b`),
			alias: 'sb-config'
		},
		// MODEL() header fields. Anchored to a following value so a bare column
		// named e.g. `ttl` in a SELECT body isn't mis-coloured.
		'sb-model-key': {
			pattern: new RegExp(`\\b(?:${alternation(MODEL_HEADER_KEYS)})\\b(?=\\s+[["'\\w(])`),
			alias: 'sb-config'
		},
		// AUDIT()/TEST() colon-form fields.
		'sb-check-key': {
			pattern: new RegExp(`\\b(?:${alternation(CHECK_HEADER_KEYS)})\\b(?=\\s*:)`),
			alias: 'sb-config'
		},
		// ref_type="reference" / ref_type="mutable"
		'sb-ref-type': {
			pattern: /\bref_type\b(?=\s*=)/,
			alias: 'sb-config'
		},
		'sb-header-value': {
			pattern: new RegExp(`\\b(?:${alternation(HEADER_VALUES)})\\b`),
			alias: 'keyword'
		},
		'sb-clickhouse': {
			pattern: new RegExp(`\\b(?:${alternation(CLICKHOUSE_KEYWORDS)})\\b`),
			alias: 'keyword'
		},
		// The normalized replay columns read as framework plumbing, not user columns.
		'sb-replay-column': {
			pattern: /\b_replay_(?:partition|offset|timestamp|landed_at|cursor)\b/,
			alias: 'sb-replay'
		}
	});

	Reflect.set(Prism.languages, 'streambuild', streambuild);
}

export function highlightStreambuild(code: string): string {
	ensureStreambuildGrammar();
	return Prism.highlight(code, Prism.languages.streambuild, 'streambuild');
}
