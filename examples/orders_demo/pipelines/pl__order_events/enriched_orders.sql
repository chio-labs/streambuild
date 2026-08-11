MODEL (
  order_by ["order_id", "event_at", "_replay_partition", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
);

SELECT
  o.order_id::String AS order_id,
  o.customer_id::String AS customer_id,
  o.product::String AS product,
  o.category::String AS category,
  o.status::String AS status,
  o.region::String AS region,
  r.region_display::String AS region_display,
  o.event_at::DateTime64(3) AS event_at,
  o._replay_partition::Int64 AS _replay_partition,
  o._replay_offset::Int64 AS _replay_offset,
  o._replay_timestamp::DateTime64(3) AS _replay_timestamp,
  o._replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __ref("orders") AS o
LEFT JOIN __ref("region_lookup", ref_type='reference') AS r ON o.region = r.region
