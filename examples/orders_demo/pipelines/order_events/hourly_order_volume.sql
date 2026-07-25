MODEL (
  engine: "SummingMergeTree()",
  order_by: ["event_hour", "region", "status"],
  partition_by: "toYYYYMM(event_hour)",
);

SELECT
  event_hour::DateTime64(3) AS event_hour,
  region::String AS region,
  status::String AS status,
  count()::UInt64 AS event_count,
  countDistinct(order_id)::UInt64 AS distinct_orders,
  countDistinct(customer_id)::UInt64 AS distinct_customers
FROM __ref("order_items")
GROUP BY event_hour, region, status
