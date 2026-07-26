from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseClientIntegrationTestCase:
    description: str
    inserted_rows: tuple[dict[str, object], ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseCatalogIntegrationTestCase:
    description: str
    expected_relation_names: frozenset[str]
    expected_stable_binding_name: str
    expected_materialized_view_source: str
    expected_materialized_view_target: str


@dataclass(frozen=True)
class InspectManagedTableStateIntegrationTestCase:
    description: str
    expected_active_bindings: tuple[tuple[str, str], ...]
    expected_physical_candidates: tuple[tuple[str, str], ...]
