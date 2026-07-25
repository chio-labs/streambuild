from dataclasses import dataclass


@dataclass(frozen=True)
class InspectRootDeploymentStateTestCase:
    description: str
    active_bindings: tuple[tuple[str, str], ...]
    physical_candidates: tuple[tuple[str, str], ...]
    expected_state_kind: str
    expected_active_deployment_id: str | None


@dataclass(frozen=True)
class BuildInspectedManagedTableStateTestCase:
    description: str
    system_rows: tuple[tuple[str, str], ...]
    expected_logical_names: tuple[str, ...]
