MODEL (
  order_by ["order_id", "event_at", "_replay_partition", "_replay_offset"],
  partition_by "toYYYYMM(event_at)",
  columns (
    order_id (audits [not_null]),
    line_total (audits [not_null (severity warning)]),
  ),
  audits [
    expression_is_true (
      name "line total non negative when present",
      expression "line_total >= 0 OR line_total IS NULL",
    ),
  ],
);

SELECT
  order_id::String AS order_id,
  customer_id::String AS customer_id,
  product::String AS product,
  category::String AS category,
  quantity::Nullable(UInt32) AS quantity,
  unit_price::Nullable(Float64) AS unit_price,
  if(isNull(quantity) OR isNull(unit_price), NULL, quantity * unit_price)::Nullable(Float64) AS line_total,
  status::String AS status,
  region::String AS region,
  event_at::DateTime64(3) AS event_at,
  toDate(event_at)::Date AS event_day,
  toStartOfHour(event_at)::DateTime64(3) AS event_hour,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp,
  _replay_landed_at::DateTime64(3) AS _replay_landed_at
FROM __ref("orders")
