MODEL (
  engine "ReplacingMergeTree(updated_at)",
  order_by ["order_id", 'updated_at'],
  partition_by "toYYYYMM(created_at)",
  description "Orders with \"escaped\" quotes and a \\ backslash",
  settings (index_granularity 8192, min_bytes_for_wide_part 0),
  retention (duration "7d", timestamp_column _replay_landed_at, when_missing skip),
  columns (
    order_id (description 'Order identifier.'),
    order_total (description "Total in major units",),
  ),
);

SELECT
  CAST(JSONExtractString(kafka_value, 'order_id') AS String) AS order_id,
  CAST(JSONExtractString(kafka_value, 'customer_id') AS String) AS customer_id,
  CAST(
    toFloat64OrNull(JSONExtractString(kafka_value, 'order_total'))
    AS Nullable(Float64)
  ) AS order_total,
  CAST(
    parseDateTime64BestEffort(
      JSONExtractString(kafka_value, 'created_at'),
      3
    )
    AS DateTime64(3)
  ) AS created_at,
  CAST(
    parseDateTime64BestEffort(
      JSONExtractString(kafka_value, 'updated_at'),
      3
    )
    AS DateTime64(3)
  ) AS updated_at,
  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at
FROM __ref("orders")
