AUDIT (
  severity: "warning",
  description: "Line totals should not be negative",
);

SELECT order_id, line_total
FROM __ref("order_items")
WHERE line_total < 0
