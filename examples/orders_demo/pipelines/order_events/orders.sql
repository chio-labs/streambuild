MODEL (
  order_by: ["order_id", "event_at", "_replay_partition", "_replay_offset"],
  partition_by: "toYYYYMM(event_at)",
  schema_change_backfill: {breaking: full, non_breaking: bounded(7d)},
);

SELECT
  JSONExtractString(kafka_value, 'order_id')::String AS order_id,
  JSONExtractString(kafka_value, 'customer_id')::String AS customer_id,
  JSONExtractString(kafka_value, 'product')::String AS product,
  JSONExtractString(kafka_value, 'category')::String AS category,
  toUInt32OrNull(JSONExtractString(kafka_value, 'quantity'))::Nullable(UInt32) AS quantity,
  toFloat64OrNull(JSONExtractString(kafka_value, 'unit_price'))::Nullable(Float64) AS unit_price,
  JSONExtractString(kafka_value, 'status')::String AS status,
  JSONExtractString(kafka_value, 'region')::String AS region,
  parseDateTime64BestEffort(
    JSONExtractString(kafka_value, 'event_at'),
    3
  )::DateTime64(3) AS event_at,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp,
  _replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __source("order_events")
