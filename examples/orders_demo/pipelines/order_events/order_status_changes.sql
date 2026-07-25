MODEL (
  order_by: ["order_id", "event_at", "_replay_partition", "_replay_offset"],
  partition_by: "toYYYYMM(event_at)",
);

SELECT
  order_id::String AS order_id,
  customer_id::String AS customer_id,
  status::String AS status,
  category::String AS category,
  region::String AS region,
  event_at::DateTime64(3) AS event_at,
  toDate(event_at)::Date AS event_day,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp,
  _replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __ref("orders")
