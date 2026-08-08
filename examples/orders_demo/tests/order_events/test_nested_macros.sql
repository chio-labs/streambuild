TEST (name "line total with nested fixture macros");

WITH __ref__orders AS (
  @mock_rows(@with_timestamps(@load_fixture("orders_simple"), "2026-04-19 10:00:00"))
),
__expected__order_items AS (
  @mock_rows([
    {"order_id": "ord_001", "line_total": 20.0},
    {"order_id": "ord_002", "line_total": 15.0}
  ])
)
SELECT 1
