AUDIT (
  severity warning,
  description "Orders should not have event_at timestamps in the future",
);

SELECT order_id, event_at
FROM __ref("orders")
WHERE event_at > now()
