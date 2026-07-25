TEST (name: "line total with mock_rows macro");

WITH __ref__orders AS (
  @mock_rows([
    {"order_id": "ord_001", "customer_id": "cust_001", "product": "Widget", "category": "electronics", "quantity": 2, "unit_price": 10.0, "status": "created", "region": "us-east", "event_at": "2026-04-19 10:00:00", "_replay_partition": 0, "_replay_offset": 1, "_replay_timestamp": "2026-04-19 10:00:00", "_replay_landed_at": "2026-04-19 10:00:00"},
    {"order_id": "ord_002", "customer_id": "cust_002", "product": "Gadget", "category": "clothing", "quantity": 3, "unit_price": 5.0, "status": "paid", "region": "eu-west", "event_at": "2026-04-19 11:00:00", "_replay_partition": 0, "_replay_offset": 2, "_replay_timestamp": "2026-04-19 11:00:00", "_replay_landed_at": "2026-04-19 11:00:00"}
  ])
),
__expected__order_items AS (
  @mock_rows([
    {"order_id": "ord_001", "line_total": 20.0},
    {"order_id": "ord_002", "line_total": 15.0}
  ])
)
SELECT 1
