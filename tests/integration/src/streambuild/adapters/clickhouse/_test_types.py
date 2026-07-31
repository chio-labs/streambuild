from dataclasses import dataclass


@dataclass(frozen=True)
class ClickHouseClientIntegrationTestCase:
    description: str
    inserted_rows: tuple[dict[str, object], ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ClickHouseWarehouseTimestampIntegrationTestCase:
    description: str
    expected_fractional_digits: int


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


@dataclass(frozen=True)
class RenderTransformMaterializedViewIntegrationTestCase:
    description: str
    expected_order_id: str
    expected_customer_id: str
    expected_order_total: float


@dataclass(frozen=True)
class MetadataMigrationIntegrationTestCase:
    description: str
    expected_table_names: tuple[str, ...]
    expected_version_rows: tuple[tuple[int], ...]


@dataclass(frozen=True)
class LegacyMetadataMigrationIntegrationTestCase:
    description: str
    runtime_details_setup_sql: str
    expected_deployment_row: tuple[str, str, str, str]
    expected_object_state_count: int
    expected_version_rows: tuple[tuple[int], ...]
    expected_legacy_deployment_count: int


@dataclass(frozen=True)
class TargetOwnershipIntegrationTestCase:
    description: str
    inserted_rows: tuple[dict[str, object], ...]
    expected_records_before_migration: tuple[tuple[str, str, str], ...]
    expected_records_after_migration: tuple[tuple[str, str, str], ...]
    expected_records_after_insert: tuple[tuple[str, str, str], ...]
