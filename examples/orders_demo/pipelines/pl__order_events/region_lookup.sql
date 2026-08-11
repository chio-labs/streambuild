MODEL (
  engine "ReplacingMergeTree()",
  order_by ["region"],
);

SELECT
  region::String AS region,
  upper(region)::String AS region_display,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp,
  _replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __ref("orders")
