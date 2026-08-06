MODEL (
  engine "SummingMergeTree()",
  order_by ["event_day", "category", "region"],
  partition_by "toYYYYMM(event_day)",
  columns (
    event_day (audits [not_null]),
    category (audits [not_null]),
  ),
  audits [
    expression_is_true (
      name "order count is positive",
      expression "order_event_count > 0",
    ),
  ],
);

SELECT
  event_day::Date AS event_day,
  category::String AS category,
  region::String AS region,
  count()::UInt64 AS order_event_count,
  countDistinct(order_id)::UInt64 AS distinct_orders,
  sumOrNull(line_total)::Nullable(Float64) AS total_revenue,
  avgOrNull(line_total)::Nullable(Float64) AS avg_order_value
FROM __ref("order_items")
WHERE status = 'created'
GROUP BY event_day, category, region
