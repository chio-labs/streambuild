MODEL (
  engine "MergeTree()",
  order_by ["order_id", "_replay_landed_at"],
);

SELECT
  JSONExtractString(kafka_value, 'order_id')::String AS order_id,
  _replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __ref("order_events")
