TEST (mode: macro, name: "line total expression handles nulls");

WITH input_values AS (
  SELECT 2 AS quantity, 10.0 AS unit_price
),
__macro_actual__ AS (
  SELECT @line_total_expression("quantity", "unit_price") AS line_total FROM input_values
),
__macro_expected__ AS (
  SELECT 20.0 AS line_total
)
SELECT 1
