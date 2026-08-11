MODEL (
  engine "MergeTree()",
  order_by ["payment_id", "_replay_landed_at"],
);

SELECT
  CAST(JSONExtractString(kafka_value, 'payment_id') AS String) AS payment_id,
  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at
FROM __ref("payments")
