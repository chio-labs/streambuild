MODEL (
  engine "MergeTree()",
  order_by ["order_id"]
);

SELECT
  order_id::String AS order_id,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __ref("idle_events")
WHERE 0
