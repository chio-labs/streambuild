TEST (name "order items never carry a negative line total");

WITH __ref__orders AS (
  @mock_rows(@with_timestamps(@load_fixture("orders_simple"), "2026-04-19 10:00:00"))
),
__assert__line_total_is_never_negative AS (
  SELECT order_id FROM __ref("order_items") WHERE line_total < 0
)
SELECT 1
