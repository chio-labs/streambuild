from dataclasses import dataclass


@dataclass(frozen=True)
class InspectManagedTableStateIntegrationTestCase:
    description: str
    expected_active_bindings: tuple[tuple[str, str], ...]
    expected_physical_candidates: tuple[tuple[str, str], ...]
