from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentInventoryTestCase:
    description: str
    deployment_statuses: tuple[tuple[str, str], ...]
    existing_deployment_ids: tuple[str, ...]
    expected_states: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PartialDeploymentInventoryTestCase:
    description: str
    expected_state: str
    expected_missing_logical_name: str
