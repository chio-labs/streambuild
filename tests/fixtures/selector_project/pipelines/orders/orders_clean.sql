MODEL (
  engine: "MergeTree()",
  order_by: ["order_id", "_replay_landed_at"],
);

SELECT
  CAST(JSONExtractString(kafka_value, 'order_id') AS String) AS order_id,
  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at
FROM __ref("orders")
