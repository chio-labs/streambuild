/**
 * SQL artifacts for the mock project.
 *
 * Four artifacts per table model, all of which StreamBuild really produces:
 *   authored   the .sql file, including its MODEL() header
 *   compiled   target/compiled/models/<pipeline>/<model>.sql — refs resolved, macros expanded
 *   tableDdl   target/compiled/resources/models/<pipeline>/<model>.table.sql
 *   mvDdl      target/compiled/resources/models/<pipeline>/<model>.mv.sql
 *
 * The MV DDL is the one users currently cannot see at all, which is a good part
 * of the reason a model detail page is worth building.
 *
 * MODEL() header grammar is StreamBuild's: whitespace-separated `key value`,
 * lists in [...], nested maps in (...), optional trailing commas. NOT `key: value`.
 * AUDIT() headers *do* use the colon form — two dialects, deliberately.
 */

import type { SqlArtifacts } from '$lib/domain/types';

const DB = 'orders_demo';

// ─── order_events pipeline ───────────────────────────────────────────────────

export const ORDERS: SqlArtifacts = {
	authored: `MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_partition", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
  settings (
    index_granularity 8192,
  ),
  replay_anchor auto,
);

SELECT
  JSONExtractString(kafka_value, 'order_id')::String       AS order_id,
  JSONExtractString(kafka_value, 'customer_id')::String    AS customer_id,
  JSONExtractString(kafka_value, 'status')::LowCardinality(String) AS status,
  JSONExtractUInt(kafka_value, 'amount_cents')::UInt64     AS amount_cents,
  JSONExtractString(kafka_value, 'region_code')::LowCardinality(String) AS region_code,
  parseDateTime64BestEffort(JSONExtractString(kafka_value, 'event_at'), 3)::DateTime64(3) AS event_at,
  _replay_partition::Int32          AS _replay_partition,
  _replay_offset::Int64             AS _replay_offset,
  _replay_timestamp::DateTime64(3)  AS _replay_timestamp,
  _replay_landed_at::DateTime64(3)  AS _replay_landed_at
FROM __source("order_events")`,
	compiled: `SELECT
  CAST(JSONExtractString(kafka_value, 'order_id') AS String) AS order_id,
  CAST(JSONExtractString(kafka_value, 'customer_id') AS String) AS customer_id,
  CAST(JSONExtractString(kafka_value, 'status') AS LowCardinality(String)) AS status,
  CAST(JSONExtractUInt(kafka_value, 'amount_cents') AS UInt64) AS amount_cents,
  CAST(JSONExtractString(kafka_value, 'region_code') AS LowCardinality(String)) AS region_code,
  CAST(parseDateTime64BestEffort(JSONExtractString(kafka_value, 'event_at'), 3) AS DateTime64(3)) AS event_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp,
  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at
FROM ${DB}.raw__order_events`,
	tableDdl: `CREATE TABLE ${DB}.tbl__orders
(
  \`order_id\` String,
  \`customer_id\` String,
  \`status\` LowCardinality(String),
  \`amount_cents\` UInt64,
  \`region_code\` LowCardinality(String),
  \`event_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3),
  \`_replay_landed_at\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_at)
ORDER BY (order_id, _replay_partition, _replay_offset)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__orders
TO ${DB}.tbl__orders
AS SELECT
  CAST(JSONExtractString(kafka_value, 'order_id') AS String) AS order_id,
  CAST(JSONExtractString(kafka_value, 'customer_id') AS String) AS customer_id,
  CAST(JSONExtractString(kafka_value, 'status') AS LowCardinality(String)) AS status,
  CAST(JSONExtractUInt(kafka_value, 'amount_cents') AS UInt64) AS amount_cents,
  CAST(JSONExtractString(kafka_value, 'region_code') AS LowCardinality(String)) AS region_code,
  CAST(parseDateTime64BestEffort(JSONExtractString(kafka_value, 'event_at'), 3) AS DateTime64(3)) AS event_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp,
  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at
FROM ${DB}.raw__order_events`,
	viewDdl: null
};

export const ORDER_ITEMS: SqlArtifacts = {
	authored: `MODEL (
  engine "MergeTree()",
  order_by ["order_id", "line_number", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
  replay_anchor auto,
);

SELECT
  o.order_id::String                AS order_id,
  item.1::UInt16                    AS line_number,
  item.2::String                    AS sku,
  item.3::UInt32                    AS quantity,
  item.4::UInt64                    AS unit_price_cents,
  @line_total_expression('item.3', 'item.4')::UInt64 AS line_total_cents,
  o.event_at::DateTime64(3)         AS event_at,
  o._replay_partition::Int32        AS _replay_partition,
  o._replay_offset::Int64           AS _replay_offset,
  o._replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __ref("orders") AS o
ARRAY JOIN arrayZip(
  arrayEnumerate(o.items), o.items.sku, o.items.quantity, o.items.unit_price_cents
) AS item`,
	compiled: `SELECT
  CAST(o.order_id AS String) AS order_id,
  CAST(item.1 AS UInt16) AS line_number,
  CAST(item.2 AS String) AS sku,
  CAST(item.3 AS UInt32) AS quantity,
  CAST(item.4 AS UInt64) AS unit_price_cents,
  CAST(item.3 * item.4 AS UInt64) AS line_total_cents,
  CAST(o.event_at AS DateTime64(3)) AS event_at,
  CAST(o._replay_partition AS Int32) AS _replay_partition,
  CAST(o._replay_offset AS Int64) AS _replay_offset,
  CAST(o._replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders AS o
ARRAY JOIN arrayZip(
  arrayEnumerate(o.items), o.items.sku, o.items.quantity, o.items.unit_price_cents
) AS item`,
	tableDdl: `CREATE TABLE ${DB}.tbl__order_items
(
  \`order_id\` String,
  \`line_number\` UInt16,
  \`sku\` String,
  \`quantity\` UInt32,
  \`unit_price_cents\` UInt64,
  \`line_total_cents\` UInt64,
  \`event_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_at)
ORDER BY (order_id, line_number, _replay_offset)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__order_items
TO ${DB}.tbl__order_items
AS SELECT
  CAST(o.order_id AS String) AS order_id,
  CAST(item.1 AS UInt16) AS line_number,
  CAST(item.2 AS String) AS sku,
  CAST(item.3 AS UInt32) AS quantity,
  CAST(item.4 AS UInt64) AS unit_price_cents,
  CAST(item.3 * item.4 AS UInt64) AS line_total_cents,
  CAST(o.event_at AS DateTime64(3)) AS event_at,
  CAST(o._replay_partition AS Int32) AS _replay_partition,
  CAST(o._replay_offset AS Int64) AS _replay_offset,
  CAST(o._replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders AS o
ARRAY JOIN arrayZip(
  arrayEnumerate(o.items), o.items.sku, o.items.quantity, o.items.unit_price_cents
) AS item`,
	viewDdl: null
};

export const ENRICHED_ORDERS: SqlArtifacts = {
	authored: `MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
);

-- region_lookup is declared mutable: its current state may differ from the
-- processing-time state, so this model can never be a replay anchor.
SELECT
  o.order_id::String                AS order_id,
  o.customer_id::String             AS customer_id,
  o.amount_cents::UInt64            AS amount_cents,
  o.region_code::LowCardinality(String) AS region_code,
  r.region_name::String             AS region_name,
  r.currency::LowCardinality(String) AS currency,
  o.event_at::DateTime64(3)         AS event_at,
  o._replay_partition::Int32        AS _replay_partition,
  o._replay_offset::Int64           AS _replay_offset,
  o._replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __ref("orders") AS o
LEFT JOIN __ref("region_lookup", ref_type="mutable") AS r
  ON o.region_code = r.region_code`,
	compiled: `SELECT
  CAST(o.order_id AS String) AS order_id,
  CAST(o.customer_id AS String) AS customer_id,
  CAST(o.amount_cents AS UInt64) AS amount_cents,
  CAST(o.region_code AS LowCardinality(String)) AS region_code,
  CAST(r.region_name AS String) AS region_name,
  CAST(r.currency AS LowCardinality(String)) AS currency,
  CAST(o.event_at AS DateTime64(3)) AS event_at,
  CAST(o._replay_partition AS Int32) AS _replay_partition,
  CAST(o._replay_offset AS Int64) AS _replay_offset,
  CAST(o._replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders AS o
LEFT JOIN ${DB}.tbl__region_lookup AS r ON o.region_code = r.region_code`,
	tableDdl: `CREATE TABLE ${DB}.tbl__enriched_orders
(
  \`order_id\` String,
  \`customer_id\` String,
  \`amount_cents\` UInt64,
  \`region_code\` LowCardinality(String),
  \`region_name\` String,
  \`currency\` LowCardinality(String),
  \`event_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_at)
ORDER BY (order_id, _replay_offset)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__enriched_orders
TO ${DB}.tbl__enriched_orders
AS SELECT
  CAST(o.order_id AS String) AS order_id,
  CAST(o.customer_id AS String) AS customer_id,
  CAST(o.amount_cents AS UInt64) AS amount_cents,
  CAST(o.region_code AS LowCardinality(String)) AS region_code,
  CAST(r.region_name AS String) AS region_name,
  CAST(r.currency AS LowCardinality(String)) AS currency,
  CAST(o.event_at AS DateTime64(3)) AS event_at,
  CAST(o._replay_partition AS Int32) AS _replay_partition,
  CAST(o._replay_offset AS Int64) AS _replay_offset,
  CAST(o._replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders AS o
LEFT JOIN ${DB}.tbl__region_lookup AS r ON o.region_code = r.region_code`,
	viewDdl: null
};

export const DAILY_REVENUE: SqlArtifacts = {
	authored: `MODEL (
  engine "AggregatingMergeTree()",
  order_by ["revenue_date", "region_code"],
  partition_by "toYYYYMM(revenue_date)",
);

-- Aggregate model: no post-aggregate replay columns are required, StreamBuild
-- places replay predicates on the input query instead.
SELECT
  toDate(i.event_at)::Date          AS revenue_date,
  o.region_code::LowCardinality(String) AS region_code,
  sumState(i.line_total_cents)::AggregateFunction(sum, UInt64) AS revenue_cents,
  uniqState(i.order_id)::AggregateFunction(uniq, String) AS order_count
FROM __ref("order_items") AS i
LEFT JOIN __ref("orders", ref_type="reference") AS o USING (order_id)
GROUP BY revenue_date, region_code`,
	compiled: `SELECT
  CAST(toDate(i.event_at) AS Date) AS revenue_date,
  CAST(o.region_code AS LowCardinality(String)) AS region_code,
  CAST(sumState(i.line_total_cents) AS AggregateFunction(sum, UInt64)) AS revenue_cents,
  CAST(uniqState(i.order_id) AS AggregateFunction(uniq, String)) AS order_count
FROM ${DB}.tbl__order_items AS i
LEFT JOIN ${DB}.tbl__orders AS o USING (order_id)
GROUP BY revenue_date, region_code`,
	tableDdl: `CREATE TABLE ${DB}.tbl__daily_revenue
(
  \`revenue_date\` Date,
  \`region_code\` LowCardinality(String),
  \`revenue_cents\` AggregateFunction(sum, UInt64),
  \`order_count\` AggregateFunction(uniq, String)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(revenue_date)
ORDER BY (revenue_date, region_code)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__daily_revenue
TO ${DB}.tbl__daily_revenue
AS SELECT
  CAST(toDate(i.event_at) AS Date) AS revenue_date,
  CAST(o.region_code AS LowCardinality(String)) AS region_code,
  CAST(sumState(i.line_total_cents) AS AggregateFunction(sum, UInt64)) AS revenue_cents,
  CAST(uniqState(i.order_id) AS AggregateFunction(uniq, String)) AS order_count
FROM ${DB}.tbl__order_items AS i
LEFT JOIN ${DB}.tbl__orders AS o USING (order_id)
GROUP BY revenue_date, region_code`,
	viewDdl: null
};

export const HOURLY_ORDER_VOLUME: SqlArtifacts = {
	authored: `MODEL (
  engine "SummingMergeTree()",
  order_by ["volume_hour", "region_code"],
  partition_by "toYYYYMM(volume_hour)",
  ttl "volume_hour + INTERVAL 180 DAY",
);

SELECT
  toStartOfHour(event_at)::DateTime AS volume_hour,
  region_code::LowCardinality(String) AS region_code,
  count()::UInt64                   AS order_count,
  sum(amount_cents)::UInt64         AS amount_cents
FROM __ref("orders")
GROUP BY volume_hour, region_code`,
	compiled: `SELECT
  CAST(toStartOfHour(event_at) AS DateTime) AS volume_hour,
  CAST(region_code AS LowCardinality(String)) AS region_code,
  CAST(count() AS UInt64) AS order_count,
  CAST(sum(amount_cents) AS UInt64) AS amount_cents
FROM ${DB}.tbl__orders
GROUP BY volume_hour, region_code`,
	tableDdl: `CREATE TABLE ${DB}.tbl__hourly_order_volume
(
  \`volume_hour\` DateTime,
  \`region_code\` LowCardinality(String),
  \`order_count\` UInt64,
  \`amount_cents\` UInt64
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(volume_hour)
ORDER BY (volume_hour, region_code)
TTL volume_hour + toIntervalDay(180)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__hourly_order_volume
TO ${DB}.tbl__hourly_order_volume
AS SELECT
  CAST(toStartOfHour(event_at) AS DateTime) AS volume_hour,
  CAST(region_code AS LowCardinality(String)) AS region_code,
  CAST(count() AS UInt64) AS order_count,
  CAST(sum(amount_cents) AS UInt64) AS amount_cents
FROM ${DB}.tbl__orders
GROUP BY volume_hour, region_code`,
	viewDdl: null
};

export const ORDER_CANCELLATIONS: SqlArtifacts = {
	authored: `MODEL (
  engine "ReplacingMergeTree(_replay_timestamp)",
  order_by ["order_id"],
  partition_by "toYYYYMM(cancelled_at)",
  replay_anchor auto,
);

SELECT
  order_id::String                  AS order_id,
  customer_id::String               AS customer_id,
  amount_cents::UInt64              AS amount_cents,
  event_at::DateTime64(3)           AS cancelled_at,
  _replay_partition::Int32          AS _replay_partition,
  _replay_offset::Int64             AS _replay_offset,
  _replay_timestamp::DateTime64(3)  AS _replay_timestamp
FROM __ref("orders")
WHERE status = 'cancelled'`,
	compiled: `SELECT
  CAST(order_id AS String) AS order_id,
  CAST(customer_id AS String) AS customer_id,
  CAST(amount_cents AS UInt64) AS amount_cents,
  CAST(event_at AS DateTime64(3)) AS cancelled_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders
WHERE status = 'cancelled'`,
	tableDdl: `CREATE TABLE ${DB}.tbl__order_cancellations
(
  \`order_id\` String,
  \`customer_id\` String,
  \`amount_cents\` UInt64,
  \`cancelled_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = ReplacingMergeTree(_replay_timestamp)
PARTITION BY toYYYYMM(cancelled_at)
ORDER BY order_id
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__order_cancellations
TO ${DB}.tbl__order_cancellations
AS SELECT
  CAST(order_id AS String) AS order_id,
  CAST(customer_id AS String) AS customer_id,
  CAST(amount_cents AS UInt64) AS amount_cents,
  CAST(event_at AS DateTime64(3)) AS cancelled_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders
WHERE status = 'cancelled'`,
	viewDdl: null
};

export const ORDER_STATUS_CHANGES: SqlArtifacts = {
	authored: `MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_timestamp"],
  partition_by "toYYYYMM(changed_at)",
  replay_anchor auto,
);

SELECT
  order_id::String                  AS order_id,
  status::LowCardinality(String)    AS status,
  event_at::DateTime64(3)           AS changed_at,
  _replay_partition::Int32          AS _replay_partition,
  _replay_offset::Int64             AS _replay_offset,
  _replay_timestamp::DateTime64(3)  AS _replay_timestamp
FROM __ref("orders")`,
	compiled: `SELECT
  CAST(order_id AS String) AS order_id,
  CAST(status AS LowCardinality(String)) AS status,
  CAST(event_at AS DateTime64(3)) AS changed_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders`,
	tableDdl: `CREATE TABLE ${DB}.tbl__order_status_changes
(
  \`order_id\` String,
  \`status\` LowCardinality(String),
  \`changed_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(changed_at)
ORDER BY (order_id, _replay_timestamp)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__order_status_changes
TO ${DB}.tbl__order_status_changes
AS SELECT
  CAST(order_id AS String) AS order_id,
  CAST(status AS LowCardinality(String)) AS status,
  CAST(event_at AS DateTime64(3)) AS changed_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.tbl__orders`,
	viewDdl: null
};

export const DAILY_CANCELLATION_RATES: SqlArtifacts = {
	authored: `MODEL (
  engine "AggregatingMergeTree()",
  order_by ["rate_date"],
  partition_by "toYYYYMM(rate_date)",
);

SELECT
  toDate(cancelled_at)::Date        AS rate_date,
  uniqState(order_id)::AggregateFunction(uniq, String) AS cancelled_orders,
  sumState(amount_cents)::AggregateFunction(sum, UInt64) AS cancelled_cents
FROM __ref("order_cancellations")
GROUP BY rate_date`,
	compiled: `SELECT
  CAST(toDate(cancelled_at) AS Date) AS rate_date,
  CAST(uniqState(order_id) AS AggregateFunction(uniq, String)) AS cancelled_orders,
  CAST(sumState(amount_cents) AS AggregateFunction(sum, UInt64)) AS cancelled_cents
FROM ${DB}.tbl__order_cancellations
GROUP BY rate_date`,
	tableDdl: `CREATE TABLE ${DB}.tbl__daily_cancellation_rates
(
  \`rate_date\` Date,
  \`cancelled_orders\` AggregateFunction(uniq, String),
  \`cancelled_cents\` AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(rate_date)
ORDER BY rate_date
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__daily_cancellation_rates
TO ${DB}.tbl__daily_cancellation_rates
AS SELECT
  CAST(toDate(cancelled_at) AS Date) AS rate_date,
  CAST(uniqState(order_id) AS AggregateFunction(uniq, String)) AS cancelled_orders,
  CAST(sumState(amount_cents) AS AggregateFunction(sum, UInt64)) AS cancelled_cents
FROM ${DB}.tbl__order_cancellations
GROUP BY rate_date`,
	viewDdl: null
};

export const AVG_FULFILLMENT_TIME: SqlArtifacts = {
	authored: `MODEL (
  engine "AggregatingMergeTree()",
  order_by ["fulfillment_date"],
  partition_by "toYYYYMM(fulfillment_date)",
  replay_anchor never,
);

-- replay_anchor never: fulfilment spans arrive out of order across the window,
-- so this model must not become a replay root.
SELECT
  toDate(changed_at)::Date          AS fulfillment_date,
  avgState(
    dateDiff('second', min(changed_at), max(changed_at))
  )::AggregateFunction(avg, Int64) AS avg_seconds
FROM __ref("order_status_changes")
GROUP BY fulfillment_date, order_id`,
	compiled: `SELECT
  CAST(toDate(changed_at) AS Date) AS fulfillment_date,
  CAST(avgState(dateDiff('second', min(changed_at), max(changed_at))) AS AggregateFunction(avg, Int64)) AS avg_seconds
FROM ${DB}.tbl__order_status_changes
GROUP BY fulfillment_date, order_id`,
	tableDdl: `CREATE TABLE ${DB}.tbl__avg_fulfillment_time
(
  \`fulfillment_date\` Date,
  \`avg_seconds\` AggregateFunction(avg, Int64)
)
ENGINE = AggregatingMergeTree()
PARTITION BY toYYYYMM(fulfillment_date)
ORDER BY fulfillment_date
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__avg_fulfillment_time
TO ${DB}.tbl__avg_fulfillment_time
AS SELECT
  CAST(toDate(changed_at) AS Date) AS fulfillment_date,
  CAST(avgState(dateDiff('second', min(changed_at), max(changed_at))) AS AggregateFunction(avg, Int64)) AS avg_seconds
FROM ${DB}.tbl__order_status_changes
GROUP BY fulfillment_date, order_id`,
	viewDdl: null
};

// ─── reference_data pipeline (adopted source) ────────────────────────────────

export const REGION_LOOKUP: SqlArtifacts = {
	authored: `MODEL (
  engine "ReplacingMergeTree(_replay_timestamp)",
  order_by ["region_code"],
  replay_anchor auto,
);

SELECT
  region_code::LowCardinality(String) AS region_code,
  region_name::String              AS region_name,
  currency::LowCardinality(String) AS currency,
  updated_cursor::Int64            AS _replay_cursor,
  updated_at::DateTime64(3)        AS _replay_timestamp
FROM __source("region_feed")`,
	compiled: `SELECT
  CAST(region_code AS LowCardinality(String)) AS region_code,
  CAST(region_name AS String) AS region_name,
  CAST(currency AS LowCardinality(String)) AS currency,
  CAST(updated_cursor AS Int64) AS _replay_cursor,
  CAST(updated_at AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.region_feed_live`,
	tableDdl: `CREATE TABLE ${DB}.tbl__region_lookup
(
  \`region_code\` LowCardinality(String),
  \`region_name\` String,
  \`currency\` LowCardinality(String),
  \`_replay_cursor\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = ReplacingMergeTree(_replay_timestamp)
ORDER BY region_code
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__region_lookup
TO ${DB}.tbl__region_lookup
AS SELECT
  CAST(region_code AS LowCardinality(String)) AS region_code,
  CAST(region_name AS String) AS region_name,
  CAST(currency AS LowCardinality(String)) AS currency,
  CAST(updated_cursor AS Int64) AS _replay_cursor,
  CAST(updated_at AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.region_feed_live`,
	viewDdl: null
};

// ─── reporting pipeline (view-only, source-less) ─────────────────────────────

export const CUSTOMER_ORDERS: SqlArtifacts = {
	authored: `MODEL (
  kind view,
  relation_name customer_orders,
);

-- A terminal view has no driving input and every reference is an ordinary query
-- dependency (no ref_type). It must have zero downstream model edges.
SELECT
  o.customer_id::String            AS customer_id,
  count(DISTINCT o.order_id)::UInt64 AS order_count,
  sum(i.line_total_cents)::UInt64  AS lifetime_cents,
  max(o.event_at)::DateTime64(3)   AS last_order_at
FROM __ref("orders") AS o
JOIN __ref("order_items") AS i USING (order_id)
GROUP BY o.customer_id`,
	compiled: `SELECT
  CAST(o.customer_id AS String) AS customer_id,
  CAST(count(DISTINCT o.order_id) AS UInt64) AS order_count,
  CAST(sum(i.line_total_cents) AS UInt64) AS lifetime_cents,
  CAST(max(o.event_at) AS DateTime64(3)) AS last_order_at
FROM ${DB}.tbl__orders AS o
JOIN ${DB}.tbl__order_items AS i USING (order_id)
GROUP BY o.customer_id`,
	tableDdl: null,
	mvDdl: null,
	viewDdl: `CREATE VIEW ${DB}.customer_orders
AS SELECT
  CAST(o.customer_id AS String) AS customer_id,
  CAST(count(DISTINCT o.order_id) AS UInt64) AS order_count,
  CAST(sum(i.line_total_cents) AS UInt64) AS lifetime_cents,
  CAST(max(o.event_at) AS DateTime64(3)) AS last_order_at
FROM ${DB}.tbl__orders AS o
JOIN ${DB}.tbl__order_items AS i USING (order_id)
GROUP BY o.customer_id`
};

// ─── source landing DDL ──────────────────────────────────────────────────────

export const KAFKA_ENGINE_DDL = `CREATE TABLE ${DB}.kafka__order_events
(
  \`kafka_value\` String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = 'redpanda:9092',
  kafka_topic_list = 'source.order_events.live',
  kafka_group_name = 'streambuild_order_events_order_events_orders_demo',
  kafka_format = 'JSONAsString',
  kafka_num_consumers = 1`;

export const LANDING_TABLE_DDL = `CREATE TABLE ${DB}.raw__order_events
(
  \`kafka_value\` String,
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3),
  \`_replay_landed_at\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(_replay_landed_at)
ORDER BY (_replay_partition, _replay_offset)
TTL _replay_landed_at + toIntervalDay(30)
SETTINGS index_granularity = 8192`;

export const LANDING_MV_DDL = `CREATE MATERIALIZED VIEW ${DB}.mv__order_events
TO ${DB}.raw__order_events
AS SELECT
  kafka_value,
  CAST(_partition AS Int32) AS _replay_partition,
  CAST(_offset AS Int64) AS _replay_offset,
  CAST(_timestamp_ms AS DateTime64(3)) AS _replay_timestamp,
  CAST(now64(3) AS DateTime64(3)) AS _replay_landed_at
FROM ${DB}.kafka__order_events`;

// ─── audit SQL ───────────────────────────────────────────────────────────────

export const AUDIT_NO_NULL_ORDER_IDS = `AUDIT (
  name: "no_null_order_ids",
  severity: "error",
  description: "Order ids must never be empty after JSON extraction",
);

SELECT order_id, event_at, _replay_offset
FROM __ref("orders")
WHERE order_id = '' OR order_id IS NULL`;

export const AUDIT_NO_FUTURE_EVENTS = `AUDIT (
  name: "no_future_events",
  severity: "warning",
  description: "Event timestamps should not be ahead of the warehouse clock",
);

SELECT order_id, event_at
FROM __ref("orders")
WHERE event_at > now64(3) + INTERVAL 1 MINUTE`;

export const AUDIT_NO_NEGATIVE_LINE_TOTALS = `AUDIT (
  name: "no_negative_line_totals",
  severity: "error",
  description: "Line totals must be non-negative",
);

SELECT order_id, line_number, line_total_cents
FROM __ref("order_items")
WHERE line_total_cents < 0`;

export const AUDIT_REVENUE_HAS_ORDERS = `AUDIT (
  name: "revenue_has_orders",
  severity: "error",
);

SELECT revenue_date, region_code
FROM __ref("daily_revenue")
WHERE uniqMerge(order_count) = 0`;

export const AUDIT_GENERIC_NOT_NULL = `AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column IS NULL`;

export const AUDIT_GENERIC_ACCEPTED_VALUES = `AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column NOT IN (@'values')`;

export const AUDIT_GENERIC_UNIQUE = `AUDIT ();

SELECT @column, count() AS occurrences
FROM __ref("@model")
GROUP BY @column
HAVING count() > 1`;

export const AUDIT_GENERIC_EXPRESSION_IS_TRUE = `AUDIT ();

SELECT *
FROM __ref("@model")
WHERE NOT (@expression)`;

// ─── test SQL ────────────────────────────────────────────────────────────────

export const TEST_LINE_TOTAL = `TEST (
  name: "line total computes correctly",
);

INPUT __ref("orders") AS (
  SELECT
    'o-1'::String AS order_id,
    [('sku-a', 3, 500)]::Array(Tuple(String, UInt32, UInt64)) AS items,
    '2026-08-01 10:00:00'::DateTime64(3) AS event_at
);

EXPECT (
  SELECT 'o-1'::String AS order_id, 1500::UInt64 AS line_total_cents
);

SELECT order_id, line_total_cents
FROM __ref("order_items")`;

export const TEST_CANCELLED_ONLY = `TEST (
  name: "cancellations only include cancelled orders",
);

INPUT __ref("orders") AS (
  SELECT * FROM @mock_rows([
    ('o-1', 'cancelled', 1200),
    ('o-2', 'paid', 900)
  ])
);

EXPECT (
  SELECT 'o-1'::String AS order_id
);

SELECT order_id FROM __ref("order_cancellations")`;

export const TEST_STATUS_VALUES = `TEST (
  name: "status changes preserve replay lineage",
);

EXPECT ZERO ROWS (
  SELECT order_id
  FROM __ref("order_status_changes")
  WHERE _replay_offset IS NULL OR _replay_timestamp IS NULL
);`;

// ─── clickstream pipeline (high-partition topic) ─────────────────────────────

export const PAGE_VIEWS: SqlArtifacts = {
	authored: `MODEL (
  engine "MergeTree()",
  order_by ["session_id", "_replay_partition", "_replay_offset"],
  partition_by "toYYYYMMDD(viewed_at)",
  replay_anchor auto,
);

SELECT
  JSONExtractString(kafka_value, 'session_id')::String   AS session_id,
  JSONExtractString(kafka_value, 'path')::String         AS path,
  JSONExtractString(kafka_value, 'referrer')::String     AS referrer,
  parseDateTime64BestEffort(JSONExtractString(kafka_value, 'viewed_at'), 3)::DateTime64(3) AS viewed_at,
  _replay_partition::Int32          AS _replay_partition,
  _replay_offset::Int64             AS _replay_offset,
  _replay_timestamp::DateTime64(3)  AS _replay_timestamp
FROM __source("page_view_events")`,
	compiled: `SELECT
  CAST(JSONExtractString(kafka_value, 'session_id') AS String) AS session_id,
  CAST(JSONExtractString(kafka_value, 'path') AS String) AS path,
  CAST(JSONExtractString(kafka_value, 'referrer') AS String) AS referrer,
  CAST(parseDateTime64BestEffort(JSONExtractString(kafka_value, 'viewed_at'), 3) AS DateTime64(3)) AS viewed_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.raw__page_view_events`,
	tableDdl: `CREATE TABLE ${DB}.tbl__page_views
(
  \`session_id\` String,
  \`path\` String,
  \`referrer\` String,
  \`viewed_at\` DateTime64(3),
  \`_replay_partition\` Int32,
  \`_replay_offset\` Int64,
  \`_replay_timestamp\` DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(viewed_at)
ORDER BY (session_id, _replay_partition, _replay_offset)
SETTINGS index_granularity = 8192`,
	mvDdl: `CREATE MATERIALIZED VIEW ${DB}.mv__page_views
TO ${DB}.tbl__page_views
AS SELECT
  CAST(JSONExtractString(kafka_value, 'session_id') AS String) AS session_id,
  CAST(JSONExtractString(kafka_value, 'path') AS String) AS path,
  CAST(JSONExtractString(kafka_value, 'referrer') AS String) AS referrer,
  CAST(parseDateTime64BestEffort(JSONExtractString(kafka_value, 'viewed_at'), 3) AS DateTime64(3)) AS viewed_at,
  CAST(_replay_partition AS Int32) AS _replay_partition,
  CAST(_replay_offset AS Int64) AS _replay_offset,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM ${DB}.raw__page_view_events`,
	viewDdl: null
};
