from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteRepairActiveViewIntegrationTestCase:
    description: str
    deployment_id: str
    expected_target_table_name: str
