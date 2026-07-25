TEST (name: "line total computes correctly");

WITH __ref__orders AS (
  SELECT
    'ord_001' AS order_id,
    'cust_001' AS customer_id,
    'Widget' AS product,
    'electronics' AS category,
    2 AS quantity,
    10.0 AS unit_price,
    'created' AS status,
    'us-east' AS region,
    toDateTime64('2026-04-19 10:00:00', 3) AS event_at,
    0 AS _replay_partition,
    1 AS _replay_offset,
    toDateTime64('2026-04-19 10:00:00', 3) AS _replay_timestamp,
    toDateTime64('2026-04-19 10:00:00', 3) AS _replay_landed_at
  UNION ALL
  SELECT
    'ord_002',
    'cust_002',
    'Gadget',
    'clothing',
    3,
    5.0,
    'cancelled',
    'eu-west',
    toDateTime64('2026-04-19 11:00:00', 3),
    0,
    2,
    toDateTime64('2026-04-19 11:00:00', 3),
    toDateTime64('2026-04-19 11:00:00', 3)
),
__expected__order_items AS (
  SELECT 'ord_001' AS order_id, 20.0 AS line_total
  UNION ALL
  SELECT 'ord_002', 15.0
)
SELECT 1

TEST (name: "null quantity yields null line total");

WITH __ref__orders AS (
  SELECT
    'ord_001' AS order_id,
    'cust_001' AS customer_id,
    'Widget' AS product,
    'electronics' AS category,
    NULL AS quantity,
    10.0 AS unit_price,
    'created' AS status,
    'us-east' AS region,
    toDateTime64('2026-04-19 10:00:00', 3) AS event_at,
    0 AS _replay_partition,
    1 AS _replay_offset,
    toDateTime64('2026-04-19 10:00:00', 3) AS _replay_timestamp,
    toDateTime64('2026-04-19 10:00:00', 3) AS _replay_landed_at
  UNION ALL
  SELECT
    'ord_002',
    'cust_002',
    'Gadget',
    'clothing',
    3,
    NULL,
    'paid',
    'eu-west',
    toDateTime64('2026-04-19 11:00:00', 3),
    0,
    2,
    toDateTime64('2026-04-19 11:00:00', 3),
    toDateTime64('2026-04-19 11:00:00', 3)
),
__expected__order_items AS (
  SELECT 'ord_001' AS order_id, NULL AS line_total
  UNION ALL
  SELECT 'ord_002' AS order_id, NULL AS line_total
)
SELECT 1
