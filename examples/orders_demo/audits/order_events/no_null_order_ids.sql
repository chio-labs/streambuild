AUDIT (
  description "order_items must not have null order_id values",
);

SELECT order_id
FROM __ref("order_items")
WHERE order_id IS NULL OR order_id = ''
