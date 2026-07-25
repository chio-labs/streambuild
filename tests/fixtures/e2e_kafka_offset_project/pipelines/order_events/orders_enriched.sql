MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT
  kafka_key::String AS order_id,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset
FROM __ref("order_events")
