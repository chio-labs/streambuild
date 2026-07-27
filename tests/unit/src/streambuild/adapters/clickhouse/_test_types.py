from dataclasses import dataclass

from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.types import AdapterReplayBoundaryMode


@dataclass(frozen=True)
class DriverErrorTranslationTestCase:
    description: str
    driver_error: Exception
    expected_error_type: type[AdapterWarehouseError]
    expected_message: str


@dataclass(frozen=True)
class ConnectionTranslationTestCase:
    description: str
    driver_error: Exception
    expected_error_type: type[AdapterWarehouseError]


@dataclass(frozen=True)
class ConnectionQueryNormalizationTestCase:
    description: str
    raw_column_names: list[str]
    raw_result_rows: list[list[object]]
    expected_column_names: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class CatalogInspectionTestCase:
    description: str
    expected_timezone: str
    expected_relation_names: frozenset[str]
    expected_query_count: int


@dataclass(frozen=True)
class ClickHousePublishCapabilitiesTestCase:
    description: str
    expected_stable_logical_bindings: bool
    expected_per_relation_atomic_replace: bool
    expected_graph_atomic_publish: bool


@dataclass(frozen=True)
class ClickHouseCleanupProtectionTestCase:
    description: str
    active_relation_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class BuildInspectedManagedTableStateTestCase:
    description: str
    system_rows: tuple[tuple[str, str], ...]
    expected_logical_names: tuple[str, ...]


@dataclass(frozen=True)
class RenderManagedSourceTestCase:
    description: str
    extra_settings: dict[str, str] | None
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RenderTableTestCase:
    description: str
    partition_by: str | None
    ttl: str | None
    settings: dict[str, str] | None
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RenderMaterializedViewTestCase:
    description: str
    query: str
    expected_source_reference: str
    expected_target_reference: str
    expected_query_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderStableViewTestCase:
    description: str
    database: str
    view_name: str
    target_table_name: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RenderMetadataStateDdlTestCase:
    description: str
    statement_index: int
    expected_sql: str


@dataclass(frozen=True)
class MetadataStateInsertStatementTestCase:
    description: str
    statement_index: int
    expected_sql: str
    expected_row: dict[str, object]


@dataclass(frozen=True)
class MetadataMigrationIdempotenceTestCase:
    description: str
    expected_version_insert_count: int
    expected_database_ensure_count: int
    expected_schema_version_ddl_fragment: str


@dataclass(frozen=True)
class MetadataMigrationInterruptionTestCase:
    description: str
    expected_version_inserts_before_recovery: int
    expected_version_inserts_after_recovery: int


@dataclass(frozen=True)
class RenderOffsetReplayStatementTestCase:
    description: str
    source_table_name: str
    target_table_name: str
    shadow_target_name: str
    anchor_table_name: str
    query: str
    replay_table_name_by_logical_name: dict[str, str]
    expected_statement: str


@dataclass(frozen=True)
class RenderAggregateOffsetPhysicalBoundaryTestCase:
    description: str
    expected_inclusive_cte_fragment: str
    expected_exclusive_cte_fragment: str
    expected_partition_predicate: str
    expected_offset_predicate: str
    expected_source_fragment: str
    expected_occurrence_count: int
    expected_absent_fragment: str


@dataclass(frozen=True)
class RenderScalarReplayBoundaryTestCase:
    description: str
    mode: AdapterReplayBoundaryMode
    boundary_key: str
    boundary_column_type: str
    cutoff_value: str
    lower_bound_value: str
    expected_lower_fragment: str
    expected_upper_fragment: str


@dataclass(frozen=True)
class ClickHouseConnectionConfigErrorTestCase:
    description: str
    values: tuple[tuple[str, object], ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class ClickHouseManagedSourceRealizationTestCase:
    description: str
    expected_relation_name: str
    expected_resource_names: tuple[str, ...]
    expected_consumer_group: str


@dataclass(frozen=True)
class ClickHouseSourceRealizationErrorTestCase:
    description: str
    source_format: str
    settings: tuple[tuple[str, str], ...]
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class ClickHouseModelRealizationTestCase:
    description: str
    expected_relation_name: str
    expected_resource_names: tuple[str, ...]
    expected_source_relation_name: str
