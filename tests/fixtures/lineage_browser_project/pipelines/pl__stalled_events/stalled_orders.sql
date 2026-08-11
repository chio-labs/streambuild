MODEL (
  engine "MergeTree()",
  order_by ["order_number"]
);

SELECT
  CAST(order_id AS UInt64) AS order_number,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __ref("stalled_events")
