AUDIT (
  description: "Daily revenue rows must have at least one order",
);

SELECT event_day, category, region, order_event_count
FROM __ref("daily_revenue")
WHERE order_event_count = 0
