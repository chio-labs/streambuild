MODEL (
  engine "SummingMergeTree()",
  order_by ["event_day", "category", "region"],
  partition_by "toYYYYMM(event_day)",
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
