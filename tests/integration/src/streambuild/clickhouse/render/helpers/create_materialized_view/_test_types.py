from dataclasses import dataclass


@dataclass(frozen=True)
class RenderTransformMaterializedViewIntegrationTestCase:
    description: str
    expected_order_id: str
    expected_customer_id: str
    expected_order_total: float
