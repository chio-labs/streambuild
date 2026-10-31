from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentDiffIntegrationTestCase:
    description: str
    expected_logical_name: str
    expected_from_row_count: int
    expected_to_row_count: int
    expected_status: str
