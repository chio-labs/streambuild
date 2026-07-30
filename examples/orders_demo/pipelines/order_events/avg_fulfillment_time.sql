MODEL (
  engine "SummingMergeTree()",
  order_by ["event_day", "category", "region"],
  partition_by "toYYYYMM(event_day)",
);

SELECT
  event_day::Date AS event_day,
  category::String AS category,
  region::String AS region,
  count()::UInt64 AS status_change_count,
  countIf(status = 'created')::UInt64 AS created_count,
  countIf(status = 'paid')::UInt64 AS paid_count,
  countIf(status = 'shipped')::UInt64 AS shipped_count,
  countIf(status = 'delivered')::UInt64 AS delivered_count,
  countIf(status = 'cancelled')::UInt64 AS cancelled_count,
  countIf(status = 'refunded')::UInt64 AS refunded_count
FROM __ref("order_status_changes")
GROUP BY event_day, category, region
