from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentInventoryTestCase:
    description: str
    deployment_statuses: tuple[tuple[str, str], ...]
    existing_deployment_ids: tuple[str, ...]
    expected_states: tuple[tuple[str, str], ...]
