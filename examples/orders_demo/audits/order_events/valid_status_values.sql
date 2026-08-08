AUDIT (
  description "Orders must have a known status value",
);

SELECT order_id, status
FROM __ref("orders")
WHERE status NOT IN ('created', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded')
