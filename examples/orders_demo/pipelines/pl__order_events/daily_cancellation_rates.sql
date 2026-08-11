MODEL (
  engine "SummingMergeTree()",
  order_by ["event_day", "region", "category"],
  partition_by "toYYYYMM(event_day)",
);

SELECT
  event_day::Date AS event_day,
  region::String AS region,
  category::String AS category,
  status::String AS cancellation_type,
  count()::UInt64 AS cancellation_count,
  countDistinct(order_id)::UInt64 AS distinct_cancelled_orders,
  countDistinct(customer_id)::UInt64 AS distinct_customers
FROM __ref("order_cancellations")
GROUP BY event_day, region, category, status
