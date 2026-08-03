/**
 * ONE mock project. Everything the UI shows is either declared here or derived
 * in `derive.ts` — never hand-authored twice.
 *
 * Modelled on StreamBuild's checked-in `examples/orders_demo`, extended so all
 * three pipeline shapes are exercised:
 *   order_events    managed Kafka source, 9 table models
 *   reference_data  adopted stream_table source (cursor boundary), 1 model
 *   reporting       view-only and source-less (valid, per the docs)
 *
 * `capturedAt` is fixed rather than `Date.now()` so screenshots and diffs stay
 * deterministic. All relative times ("2s ago") are computed against it.
 */

import type {
	Audit,
	Column,
	Macro,
	Model,
	PartitionState,
	Pipeline,
	Project,
	Source,
	SqlTest
} from '$lib/domain/types';
import * as SQL from '$lib/domain/sql';

/** Fixed warehouse clock for the whole fixture. */
export const CAPTURED_AT = '2026-08-02T12:04:33.412Z';

const REPLAY_COLS_OFFSETS: Column[] = [
	{ name: '_replay_partition', type: 'Int32', replayRole: 'partition', description: null },
	{ name: '_replay_offset', type: 'Int64', replayRole: 'offset', description: null },
	{ name: '_replay_timestamp', type: 'DateTime64(3)', replayRole: 'timestamp', description: null }
];

// ─── sources ─────────────────────────────────────────────────────────────────

const ORDER_EVENTS_SOURCE: Source = {
	name: 'order_events',
	kind: 'kafka',
	boundaryMode: 'offsets',
	relationName: 'raw__order_events',
	managedRelations: [
		{
			kind: 'kafka_engine',
			name: 'kafka__order_events',
			engine: 'Kafka',
			note: 'consumes the topic'
		},
		{
			kind: 'landing_mv',
			name: 'mv__order_events',
			engine: 'MaterializedView',
			note: 'writes retained history'
		},
		{
			kind: 'landing_table',
			name: 'raw__order_events',
			engine: 'MergeTree',
			note: 'the system of record'
		}
	],
	ttl: '_replay_landed_at + INTERVAL 30 DAY',
	retentionDays: 30,
	ttlFromProjectDefault: true,
	brokerList: 'redpanda:9092',
	topic: 'source.order_events.live',
	consumerGroup: 'streambuild_order_events_order_events_orders_demo',
	format: 'JSONAsString',
	settings: { kafka_num_consumers: '1' },
	columnMapping: null,
	live: {
		rowsPerSecond: 1240,
		lagSeconds: 2.1,
		newestEventAt: '2026-08-02T12:04:31.880Z',
		oldestEventAt: '2026-07-03T12:11:04.000Z',
		rows: 41203112,
		partitions: [
			{
				partition: 0,
				offset: 1204551,
				lagSeconds: 0.4,
				newestEventAt: '2026-08-02T12:04:31.880Z'
			},
			{
				partition: 1,
				offset: 1198220,
				lagSeconds: 0.6,
				newestEventAt: '2026-08-02T12:04:31.640Z'
			},
			{
				partition: 2,
				offset: 1201003,
				lagSeconds: 0.5,
				newestEventAt: '2026-08-02T12:04:31.720Z'
			},
			{
				partition: 3,
				offset: 998410,
				lagSeconds: 41.2,
				newestEventAt: '2026-08-02T12:03:50.410Z'
			}
		],
		throughput: [
			980, 1010, 1120, 1180, 1240, 1310, 1280, 1190, 1140, 1220, 1300, 1420, 1380, 1250, 1160,
			1090, 1170, 1240, 1290, 1240
		]
	}
};

const REGION_FEED_SOURCE: Source = {
	name: 'region_feed',
	kind: 'stream_table',
	boundaryMode: 'cursor',
	relationName: 'region_feed_live',
	managedRelations: [],
	ttl: null,
	retentionDays: null,
	ttlFromProjectDefault: false,
	brokerList: null,
	topic: null,
	consumerGroup: null,
	format: null,
	settings: null,
	columnMapping: {
		cursor: 'updated_cursor',
		timestamp: 'updated_at'
	},
	live: {
		rowsPerSecond: 0.3,
		lagSeconds: null,
		newestEventAt: '2026-08-02T11:58:12.000Z',
		oldestEventAt: '2025-11-14T09:20:00.000Z',
		rows: 412,
		partitions: [],
		throughput: [0, 1, 0, 0, 2, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0]
	}
};


/**
 * A deliberately high-partition topic. Plenty of real deployments run hundreds
 * or thousands of partitions, and both the Overview strip and the partition
 * table have to stay usable at that size — this keeps that honest.
 */
const PAGE_VIEW_PARTITION_COUNT: number = 128;

function buildPageViewPartitions(): PartitionState[] {
	const partitions: PartitionState[] = [];
	for (let index = 0; index < PAGE_VIEW_PARTITION_COUNT; index += 1) {
		// Deterministic pseudo-jitter so screenshots stay stable.
		const jitter: number = ((index * 37) % 11) / 10;
		const straggler: boolean = index % 29 === 0;
		const lagSeconds: number = straggler ? 60 + ((index * 13) % 240) : 0.3 + jitter;
		const offsetMillis: number = Math.round(lagSeconds * 1000);
		partitions.push({
			partition: index,
			offset: 8_400_000 + index * 1237,
			lagSeconds,
			newestEventAt: new Date(
				new Date('2026-08-02T12:04:32.000Z').getTime() - offsetMillis
			).toISOString()
		});
	}
	return partitions;
}

const PAGE_VIEW_EVENTS_SOURCE: Source = {
	name: 'page_view_events',
	kind: 'kafka',
	boundaryMode: 'offsets',
	relationName: 'raw__page_view_events',
	managedRelations: [
		{
			kind: 'kafka_engine',
			name: 'kafka__page_view_events',
			engine: 'Kafka',
			note: 'consumes the topic'
		},
		{
			kind: 'landing_mv',
			name: 'mv__page_view_events',
			engine: 'MaterializedView',
			note: 'writes retained history'
		},
		{
			kind: 'landing_table',
			name: 'raw__page_view_events',
			engine: 'MergeTree',
			note: 'the system of record'
		}
	],
	ttl: '_replay_landed_at + INTERVAL 7 DAY',
	retentionDays: 7,
	ttlFromProjectDefault: false,
	brokerList: 'redpanda:9092',
	topic: 'source.page_views.live',
	consumerGroup: 'streambuild_page_view_events_page_view_events_orders_demo',
	format: 'JSONAsString',
	settings: { kafka_num_consumers: '4' },
	columnMapping: null,
	live: {
		rowsPerSecond: 18400,
		lagSeconds: 96.4,
		newestEventAt: '2026-08-02T12:04:32.000Z',
		oldestEventAt: '2026-07-26T12:04:33.000Z',
		rows: 1104882301,
		partitions: buildPageViewPartitions(),
		throughput: [
			17200, 17800, 18100, 18900, 19400, 18700, 18200, 17900, 18400, 19100, 19800, 20200, 19400,
			18800, 18100, 17600, 18000, 18300, 18600, 18400
		]
	}
};

// ─── models ──────────────────────────────────────────────────────────────────

const MODELS: Model[] = [
	{
		name: 'page_views',
		pipeline: 'clickstream',
		kind: 'table',
		description: 'Raw page views parsed from a high-partition clickstream topic.',
		relationName: 'tbl__page_views',
		mvRelationName: 'mv__page_views',
		drivingInput: 'page_view_events',
		refs: [{ name: 'page_view_events', type: 'driving_input', alias: null, isSource: true }],
		columns: [
			{ name: 'session_id', type: 'String', replayRole: null, description: null },
			{ name: 'path', type: 'String', replayRole: null, description: null },
			{ name: 'referrer', type: 'String', replayRole: null, description: null },
			{ name: 'viewed_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS
		],
		storage: {
			engine: 'MergeTree()',
			orderBy: ['session_id', '_replay_partition', '_replay_offset'],
			partitionBy: 'toYYYYMMDD(viewed_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.PAGE_VIEWS,
		live: {
			rows: 1104882301,
			diskBytes: 91268055040,
			parts: 412,
			newestRowAt: '2026-08-02T12:02:56.000Z',
			oldestRowAt: '2026-07-26T12:04:33.000Z',
			lagSeconds: 97.1,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-26T12:04:33.000Z', to: '2026-08-02T12:02:56.000Z' }
		},
		status: 'lagging'
	},
	{
		name: 'orders',
		pipeline: 'order_events',
		kind: 'table',
		description: 'One row per order event, parsed from the Kafka JSON payload.',
		relationName: 'tbl__orders',
		mvRelationName: 'mv__orders',
		drivingInput: 'order_events',
		refs: [{ name: 'order_events', type: 'driving_input', alias: null, isSource: true }],
		columns: [
			{ name: 'order_id', type: 'String', replayRole: null, description: 'Business key' },
			{ name: 'customer_id', type: 'String', replayRole: null, description: null },
			{ name: 'status', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'amount_cents', type: 'UInt64', replayRole: null, description: null },
			{ name: 'region_code', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'event_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS,
			{
				name: '_replay_landed_at',
				type: 'DateTime64(3)',
				replayRole: 'landed_at',
				description: null
			}
		],
		storage: {
			engine: 'MergeTree()',
			orderBy: ['order_id', '_replay_partition', '_replay_offset'],
			partitionBy: 'toYYYYMM(event_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.ORDERS,
		live: {
			rows: 41203112,
			diskBytes: 3435973836,
			parts: 84,
			newestRowAt: '2026-08-02T12:04:31.880Z',
			oldestRowAt: '2026-07-03T12:11:04.000Z',
			lagSeconds: 2.1,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:04:31.880Z' }
		},
		status: 'fresh'
	},
	{
		name: 'order_items',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Order lines exploded from the order payload, with computed line totals.',
		relationName: 'tbl__order_items',
		mvRelationName: 'mv__order_items',
		drivingInput: 'orders',
		refs: [{ name: 'orders', type: 'driving_input', alias: 'o', isSource: false }],
		columns: [
			{ name: 'order_id', type: 'String', replayRole: null, description: null },
			{ name: 'line_number', type: 'UInt16', replayRole: null, description: null },
			{ name: 'sku', type: 'String', replayRole: null, description: null },
			{ name: 'quantity', type: 'UInt32', replayRole: null, description: null },
			{ name: 'unit_price_cents', type: 'UInt64', replayRole: null, description: null },
			{
				name: 'line_total_cents',
				type: 'UInt64',
				replayRole: null,
				description: 'quantity * unit_price_cents, via @line_total_expression'
			},
			{ name: 'event_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS
		],
		storage: {
			engine: 'MergeTree()',
			orderBy: ['order_id', 'line_number', '_replay_offset'],
			partitionBy: 'toYYYYMM(event_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.ORDER_ITEMS,
		live: {
			rows: 118412904,
			diskBytes: 8697308774,
			parts: 142,
			newestRowAt: '2026-08-02T12:04:31.410Z',
			oldestRowAt: '2026-07-03T12:11:04.000Z',
			lagSeconds: 2.4,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:04:31.410Z' }
		},
		status: 'fresh'
	},
	{
		name: 'enriched_orders',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Orders joined to region reference data. Cannot be a replay anchor.',
		relationName: 'tbl__enriched_orders',
		mvRelationName: 'mv__enriched_orders',
		drivingInput: 'orders',
		refs: [
			{ name: 'orders', type: 'driving_input', alias: 'o', isSource: false },
			{ name: 'region_lookup', type: 'mutable_reference', alias: 'r', isSource: false }
		],
		columns: [
			{ name: 'order_id', type: 'String', replayRole: null, description: null },
			{ name: 'customer_id', type: 'String', replayRole: null, description: null },
			{ name: 'amount_cents', type: 'UInt64', replayRole: null, description: null },
			{ name: 'region_code', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'region_name', type: 'String', replayRole: null, description: null },
			{ name: 'currency', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'event_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS
		],
		storage: {
			engine: 'MergeTree()',
			orderBy: ['order_id', '_replay_offset'],
			partitionBy: 'toYYYYMM(event_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'mutable_ref',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.ENRICHED_ORDERS,
		live: {
			rows: 41203090,
			diskBytes: 4724464025,
			parts: 91,
			newestRowAt: '2026-08-02T12:04:30.220Z',
			oldestRowAt: '2026-07-03T12:11:04.000Z',
			lagSeconds: 3.1,
			inSyncWithCompiled: false,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:04:30.220Z' }
		},
		status: 'drift'
	},
	{
		name: 'daily_revenue',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Daily revenue rollup by region. Retained far beyond source history.',
		relationName: 'tbl__daily_revenue',
		mvRelationName: 'mv__daily_revenue',
		drivingInput: 'order_items',
		refs: [
			{ name: 'order_items', type: 'driving_input', alias: 'i', isSource: false },
			{ name: 'orders', type: 'reference', alias: 'o', isSource: false }
		],
		columns: [
			{ name: 'revenue_date', type: 'Date', replayRole: null, description: null },
			{ name: 'region_code', type: 'LowCardinality(String)', replayRole: null, description: null },
			{
				name: 'revenue_cents',
				type: 'AggregateFunction(sum, UInt64)',
				replayRole: null,
				description: 'Merge with sumMerge()'
			},
			{
				name: 'order_count',
				type: 'AggregateFunction(uniq, String)',
				replayRole: null,
				description: 'Merge with uniqMerge()'
			}
		],
		storage: {
			engine: 'AggregatingMergeTree()',
			orderBy: ['revenue_date', 'region_code'],
			partitionBy: 'toYYYYMM(revenue_date)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'aggregate',
		isAggregate: true,
		anchorNever: false,
		sql: SQL.DAILY_REVENUE,
		live: {
			rows: 5412,
			diskBytes: 43220992,
			parts: 12,
			newestRowAt: '2026-08-02T00:00:00.000Z',
			oldestRowAt: '2026-02-01T00:00:00.000Z',
			lagSeconds: 4.2,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:04:29.000Z' }
		},
		status: 'fresh'
	},
	{
		name: 'hourly_order_volume',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Hourly order counts by region.',
		relationName: 'tbl__hourly_order_volume',
		mvRelationName: 'mv__hourly_order_volume',
		drivingInput: 'orders',
		refs: [{ name: 'orders', type: 'driving_input', alias: null, isSource: false }],
		columns: [
			{ name: 'volume_hour', type: 'DateTime', replayRole: null, description: null },
			{ name: 'region_code', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'order_count', type: 'UInt64', replayRole: null, description: null },
			{ name: 'amount_cents', type: 'UInt64', replayRole: null, description: null }
		],
		storage: {
			engine: 'SummingMergeTree()',
			orderBy: ['volume_hour', 'region_code'],
			partitionBy: 'toYYYYMM(volume_hour)',
			ttl: 'volume_hour + INTERVAL 180 DAY',
			settings: { index_granularity: '8192' }
		},
		anchor: 'aggregate',
		isAggregate: true,
		anchorNever: false,
		sql: SQL.HOURLY_ORDER_VOLUME,
		live: {
			rows: 18240,
			diskBytes: 8912896,
			parts: 9,
			newestRowAt: '2026-08-02T12:00:00.000Z',
			oldestRowAt: '2026-07-03T13:00:00.000Z',
			lagSeconds: 5.8,
			inSyncWithCompiled: false,
			ownership: 'unmanaged',
			recordedCoverage: null
		},
		status: 'drift'
	},
	{
		name: 'order_cancellations',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Cancelled orders only, deduplicated on the latest replay timestamp.',
		relationName: 'tbl__order_cancellations',
		mvRelationName: 'mv__order_cancellations',
		drivingInput: 'orders',
		refs: [{ name: 'orders', type: 'driving_input', alias: null, isSource: false }],
		columns: [
			{ name: 'order_id', type: 'String', replayRole: null, description: null },
			{ name: 'customer_id', type: 'String', replayRole: null, description: null },
			{ name: 'amount_cents', type: 'UInt64', replayRole: null, description: null },
			{ name: 'cancelled_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS
		],
		storage: {
			engine: 'ReplacingMergeTree(_replay_timestamp)',
			orderBy: ['order_id'],
			partitionBy: 'toYYYYMM(cancelled_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.ORDER_CANCELLATIONS,
		live: {
			rows: 812044,
			diskBytes: 96468992,
			parts: 22,
			newestRowAt: '2026-08-02T12:03:58.100Z',
			oldestRowAt: '2026-07-03T12:44:19.000Z',
			lagSeconds: 35.3,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:44:19.000Z', to: '2026-08-02T12:03:58.100Z' }
		},
		status: 'fresh'
	},
	{
		name: 'order_status_changes',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Every status transition, preserving full replay lineage.',
		relationName: 'tbl__order_status_changes',
		mvRelationName: 'mv__order_status_changes',
		drivingInput: 'orders',
		refs: [{ name: 'orders', type: 'driving_input', alias: null, isSource: false }],
		columns: [
			{ name: 'order_id', type: 'String', replayRole: null, description: null },
			{ name: 'status', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'changed_at', type: 'DateTime64(3)', replayRole: null, description: null },
			...REPLAY_COLS_OFFSETS
		],
		storage: {
			engine: 'MergeTree()',
			orderBy: ['order_id', '_replay_timestamp'],
			partitionBy: 'toYYYYMM(changed_at)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.ORDER_STATUS_CHANGES,
		live: {
			rows: 8140922,
			diskBytes: 712179712,
			parts: 41,
			newestRowAt: '2026-08-02T12:04:29.740Z',
			oldestRowAt: '2026-07-03T12:11:04.000Z',
			lagSeconds: 3.7,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:04:29.740Z' }
		},
		status: 'fresh'
	},
	{
		name: 'daily_cancellation_rates',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Daily cancellation rollup. Retained far beyond source history.',
		relationName: 'tbl__daily_cancellation_rates',
		mvRelationName: 'mv__daily_cancellation_rates',
		drivingInput: 'order_cancellations',
		refs: [{ name: 'order_cancellations', type: 'driving_input', alias: null, isSource: false }],
		columns: [
			{ name: 'rate_date', type: 'Date', replayRole: null, description: null },
			{
				name: 'cancelled_orders',
				type: 'AggregateFunction(uniq, String)',
				replayRole: null,
				description: null
			},
			{
				name: 'cancelled_cents',
				type: 'AggregateFunction(sum, UInt64)',
				replayRole: null,
				description: null
			}
		],
		storage: {
			engine: 'AggregatingMergeTree()',
			orderBy: ['rate_date'],
			partitionBy: 'toYYYYMM(rate_date)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'aggregate',
		isAggregate: true,
		anchorNever: false,
		sql: SQL.DAILY_CANCELLATION_RATES,
		live: {
			rows: 412,
			diskBytes: 2097152,
			parts: 6,
			newestRowAt: '2026-08-02T07:52:15.000Z',
			oldestRowAt: '2026-02-01T00:00:00.000Z',
			lagSeconds: 15138,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:44:19.000Z', to: '2026-08-02T07:52:15.000Z' }
		},
		status: 'stalled'
	},
	{
		name: 'avg_fulfillment_time',
		pipeline: 'order_events',
		kind: 'table',
		description: 'Average fulfilment span per day. Explicitly excluded as a replay anchor.',
		relationName: 'tbl__avg_fulfillment_time',
		mvRelationName: 'mv__avg_fulfillment_time',
		drivingInput: 'order_status_changes',
		refs: [{ name: 'order_status_changes', type: 'driving_input', alias: null, isSource: false }],
		columns: [
			{ name: 'fulfillment_date', type: 'Date', replayRole: null, description: null },
			{
				name: 'avg_seconds',
				type: 'AggregateFunction(avg, Int64)',
				replayRole: null,
				description: null
			}
		],
		storage: {
			engine: 'AggregatingMergeTree()',
			orderBy: ['fulfillment_date'],
			partitionBy: 'toYYYYMM(fulfillment_date)',
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'never',
		isAggregate: true,
		anchorNever: true,
		sql: SQL.AVG_FULFILLMENT_TIME,
		live: {
			rows: 5104,
			diskBytes: 3145728,
			parts: 8,
			newestRowAt: '2026-08-02T12:03:55.000Z',
			oldestRowAt: '2026-07-03T00:00:00.000Z',
			lagSeconds: 38.4,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2026-07-03T12:11:04.000Z', to: '2026-08-02T12:03:55.000Z' }
		},
		status: 'lagging'
	},
	{
		name: 'region_lookup',
		pipeline: 'reference_data',
		kind: 'table',
		description: 'Region reference data adopted from an existing ClickHouse table.',
		relationName: 'tbl__region_lookup',
		mvRelationName: 'mv__region_lookup',
		drivingInput: 'region_feed',
		refs: [{ name: 'region_feed', type: 'driving_input', alias: null, isSource: true }],
		columns: [
			{ name: 'region_code', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: 'region_name', type: 'String', replayRole: null, description: null },
			{ name: 'currency', type: 'LowCardinality(String)', replayRole: null, description: null },
			{ name: '_replay_cursor', type: 'Int64', replayRole: 'cursor', description: null },
			{
				name: '_replay_timestamp',
				type: 'DateTime64(3)',
				replayRole: 'timestamp',
				description: null
			}
		],
		storage: {
			engine: 'ReplacingMergeTree(_replay_timestamp)',
			orderBy: ['region_code'],
			partitionBy: null,
			ttl: null,
			settings: { index_granularity: '8192' }
		},
		anchor: 'eligible',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.REGION_LOOKUP,
		live: {
			rows: 412,
			diskBytes: 262144,
			parts: 3,
			newestRowAt: '2026-08-02T11:58:12.000Z',
			oldestRowAt: '2025-11-14T09:20:00.000Z',
			lagSeconds: 381,
			inSyncWithCompiled: true,
			ownership: 'direct',
			recordedCoverage: { from: '2025-11-14T09:20:00.000Z', to: '2026-08-02T11:58:12.000Z' }
		},
		status: 'fresh'
	},
	{
		name: 'customer_orders',
		pipeline: 'reporting',
		kind: 'view',
		description: 'Terminal view: per-customer order rollup. No downstream model edges.',
		relationName: 'customer_orders',
		mvRelationName: null,
		drivingInput: null,
		refs: [
			{ name: 'orders', type: 'reference', alias: 'o', isSource: false },
			{ name: 'order_items', type: 'reference', alias: 'i', isSource: false }
		],
		columns: [
			{ name: 'customer_id', type: 'String', replayRole: null, description: null },
			{ name: 'order_count', type: 'UInt64', replayRole: null, description: null },
			{ name: 'lifetime_cents', type: 'UInt64', replayRole: null, description: null },
			{ name: 'last_order_at', type: 'DateTime64(3)', replayRole: null, description: null }
		],
		storage: { engine: null, orderBy: [], partitionBy: null, ttl: null, settings: null },
		anchor: 'view',
		isAggregate: false,
		anchorNever: false,
		sql: SQL.CUSTOMER_ORDERS,
		live: {
			rows: 0,
			diskBytes: 0,
			parts: 0,
			newestRowAt: null,
			oldestRowAt: null,
			lagSeconds: null,
			inSyncWithCompiled: false,
			ownership: 'direct',
			recordedCoverage: null
		},
		status: 'drift'
	}
];

// ─── pipelines ───────────────────────────────────────────────────────────────

const PIPELINES: Pipeline[] = [
	{
		name: 'order_events',
		sourceName: 'order_events',
		boundaryMode: 'offsets',
		models: [
			'orders',
			'order_items',
			'enriched_orders',
			'daily_revenue',
			'hourly_order_volume',
			'order_cancellations',
			'order_status_changes',
			'daily_cancellation_rates',
			'avg_fulfillment_time'
		],
		naming: null,
		directory: 'pipelines/order_events'
	},
	{
		name: 'clickstream',
		sourceName: 'page_view_events',
		boundaryMode: 'offsets',
		models: ['page_views'],
		naming: null,
		directory: 'pipelines/clickstream'
	},
	{
		name: 'reference_data',
		sourceName: 'region_feed',
		boundaryMode: 'cursor',
		models: ['region_lookup'],
		naming: null,
		directory: 'pipelines/reference_data'
	},
	{
		name: 'reporting',
		sourceName: null,
		boundaryMode: null,
		models: ['customer_orders'],
		naming: { tablePrefix: null, viewPrefix: 'reporting__' },
		directory: 'pipelines/reporting'
	}
];

// ─── audits ──────────────────────────────────────────────────────────────────

const CHECKED_AT = '2026-08-02T11:58:24.000Z';

const AUDITS: Audit[] = [
	{
		name: 'no_null_order_ids',
		file: 'audits/order_events/no_null_order_ids.sql',
		severity: 'error',
		description: 'Order ids must never be empty after JSON extraction',
		referencedModels: ['orders'],
		generic: false,
		genericName: null,
		sql: SQL.AUDIT_NO_NULL_ORDER_IDS,
		result: {
			passed: false,
			failingRowCount: 142,
			sampleColumns: ['order_id', 'event_at', '_replay_offset'],
			sampleRows: [
				['', '2026-08-02 11:58:02.114', 1204488],
				['', '2026-08-02 11:57:41.902', 1204402],
				['', '2026-08-02 11:56:03.551', 1204219],
				['', '2026-08-02 11:52:18.004', 1203871],
				['', '2026-08-02 11:49:55.720', 1203602]
			],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'no_future_events',
		file: 'audits/order_events/no_future_events.sql',
		severity: 'warning',
		description: 'Event timestamps should not be ahead of the warehouse clock',
		referencedModels: ['orders'],
		generic: false,
		genericName: null,
		sql: SQL.AUDIT_NO_FUTURE_EVENTS,
		result: {
			passed: false,
			failingRowCount: 3,
			sampleColumns: ['order_id', 'event_at'],
			sampleRows: [
				['ord_8841204', '2026-08-02 12:09:14.000'],
				['ord_8841190', '2026-08-02 12:07:02.000'],
				['ord_8841166', '2026-08-02 12:06:41.000']
			],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'no_negative_line_totals',
		file: 'audits/order_events/no_negative_line_totals.sql',
		severity: 'error',
		description: 'Line totals must be non-negative',
		referencedModels: ['order_items'],
		generic: false,
		genericName: null,
		sql: SQL.AUDIT_NO_NEGATIVE_LINE_TOTALS,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'revenue_has_orders',
		file: 'audits/order_events/revenue_has_orders.sql',
		severity: 'error',
		description: null,
		referencedModels: ['daily_revenue'],
		generic: false,
		genericName: null,
		sql: SQL.AUDIT_REVENUE_HAS_ORDERS,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'orders.order_id.not_null',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['orders'],
		generic: true,
		genericName: 'not_null',
		sql: SQL.AUDIT_GENERIC_NOT_NULL,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'orders.customer_id.not_null',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['orders'],
		generic: true,
		genericName: 'not_null',
		sql: SQL.AUDIT_GENERIC_NOT_NULL,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'orders.status.accepted_values',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['orders'],
		generic: true,
		genericName: 'accepted_values',
		sql: SQL.AUDIT_GENERIC_ACCEPTED_VALUES,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'orders.amount_cents.expression_is_true',
		file: 'pipelines/order_events/schema.yml',
		severity: 'warning',
		description: 'amount_cents >= 0',
		referencedModels: ['orders'],
		generic: true,
		genericName: 'expression_is_true',
		sql: SQL.AUDIT_GENERIC_EXPRESSION_IS_TRUE,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'order_items.sku.not_null',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['order_items'],
		generic: true,
		genericName: 'not_null',
		sql: SQL.AUDIT_GENERIC_NOT_NULL,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'order_items.quantity.expression_is_true',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: 'quantity > 0',
		referencedModels: ['order_items'],
		generic: true,
		genericName: 'expression_is_true',
		sql: SQL.AUDIT_GENERIC_EXPRESSION_IS_TRUE,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'daily_revenue.revenue_date.not_null',
		file: 'pipelines/order_events/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['daily_revenue'],
		generic: true,
		genericName: 'not_null',
		sql: SQL.AUDIT_GENERIC_NOT_NULL,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'region_lookup.region_code.unique',
		file: 'pipelines/reference_data/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['region_lookup'],
		generic: true,
		genericName: 'unique',
		sql: SQL.AUDIT_GENERIC_UNIQUE,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	},
	{
		name: 'region_lookup.currency.accepted_values',
		file: 'pipelines/reference_data/schema.yml',
		severity: 'error',
		description: null,
		referencedModels: ['region_lookup'],
		generic: true,
		genericName: 'accepted_values',
		sql: SQL.AUDIT_GENERIC_ACCEPTED_VALUES,
		result: {
			passed: true,
			failingRowCount: 0,
			sampleColumns: [],
			sampleRows: [],
			checkedAt: CHECKED_AT
		}
	}
];

// ─── tests ───────────────────────────────────────────────────────────────────

const TESTS: SqlTest[] = [
	{
		name: 'line total computes correctly',
		file: 'tests/order_events/test_line_total.sql',
		targets: ['order_items'],
		sql: SQL.TEST_LINE_TOTAL,
		result: {
			passed: false,
			columns: ['order_id', 'line_total_cents'],
			missingRows: [['o-1', 1500]],
			unexpectedRows: [['o-1', 1499]],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'cancellations only include cancelled orders',
		file: 'tests/order_events/test_order_item_assertions.sql',
		targets: ['order_cancellations'],
		sql: SQL.TEST_CANCELLED_ONLY,
		result: {
			passed: true,
			columns: ['order_id'],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'status changes preserve replay lineage',
		file: 'tests/order_events/test_with_macros.sql',
		targets: ['order_status_changes'],
		sql: SQL.TEST_STATUS_VALUES,
		result: {
			passed: true,
			columns: [],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'line total macro expands',
		file: 'tests/order_events/test_line_total_macro.sql',
		targets: ['order_items'],
		sql: SQL.TEST_LINE_TOTAL,
		result: {
			passed: true,
			columns: ['order_id', 'line_total_cents'],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'nested macros resolve',
		file: 'tests/order_events/test_nested_macros.sql',
		targets: ['order_items'],
		sql: SQL.TEST_LINE_TOTAL,
		result: {
			passed: true,
			columns: ['order_id', 'line_total_cents'],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'orders and items agree on order count',
		file: 'tests/order_events/test_chain_totals.sql',
		targets: ['orders', 'order_items'],
		sql: SQL.TEST_LINE_TOTAL,
		result: {
			passed: true,
			columns: ['order_id'],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	},
	{
		name: 'region lookup dedupes on cursor',
		file: 'tests/reference_data/test_region_dedupe.sql',
		targets: ['region_lookup'],
		sql: SQL.TEST_CANCELLED_ONLY,
		result: {
			passed: true,
			columns: ['region_code'],
			missingRows: [],
			unexpectedRows: [],
			checkedAt: CHECKED_AT,
			errorMessage: null
		}
	}
];

// ─── macros ──────────────────────────────────────────────────────────────────

const MACROS: Macro[] = [
	{
		name: 'line_total_expression',
		file: 'macros/common.py',
		signature: 'line_total_expression(quantity, unit_price)',
		description: 'Multiplies quantity by unit price as a raw SQL expression.'
	},
	{
		name: 'mock_rows',
		file: 'macros/common.py',
		signature: 'mock_rows(rows)',
		description: 'Builds a VALUES-style literal block for test inputs.'
	},
	{
		name: 'load_fixture',
		file: 'macros/common.py',
		signature: 'load_fixture(name)',
		description: 'Inlines a CSV fixture as a SELECT.'
	},
	{
		name: 'replay_columns',
		file: 'macros/common.py',
		signature: 'replay_columns(mode)',
		description: 'Emits the normalized replay projections for a boundary mode.'
	},
	{
		name: 'timestamp_literal',
		file: 'macros/common.py',
		signature: 'timestamp_literal(value)',
		description: 'Renders a DateTime64(3) literal.'
	},
	{
		name: 'with_timestamps',
		file: 'macros/common.py',
		signature: 'with_timestamps(select)',
		description: 'Appends standard timestamp columns to a projection.'
	}
];

// ─── project ─────────────────────────────────────────────────────────────────

export const PROJECT: Project = {
	name: 'orders_demo',
	target: 'prod',
	database: 'orders_demo',
	adapter: 'clickhouse',
	virtualEnvironments: false,
	connection: { host: 'clickhouse.internal', port: 8443, username: 'streambuild', secure: true },
	vars: { revenue_currency: 'USD', late_arrival_grace_seconds: 120, enable_region_join: true },
	naming: { tablePrefix: 'tbl__', viewPrefix: 'view__' },
	defaults: { managedSourceTtl: '_replay_landed_at + INTERVAL 30 DAY' },
	toolVersion: '0.9.2',
	warehouseTimezone: 'UTC',
	capturedAt: CAPTURED_AT,
	sources: [ORDER_EVENTS_SOURCE, PAGE_VIEW_EVENTS_SOURCE, REGION_FEED_SOURCE],
	pipelines: PIPELINES,
	models: MODELS,
	audits: AUDITS,
	tests: TESTS,
	macros: MACROS
};
