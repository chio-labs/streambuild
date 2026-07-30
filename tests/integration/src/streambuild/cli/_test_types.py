from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
)


class CliManagedSourceResources(NamedTuple):
    kafka_table: DesiredKafkaTable
    raw_table: DesiredTable
    materialized_view: DesiredMaterializedView


@dataclass(frozen=True)
class CliBackfillIntegrationTestCase:
    description: str
    pipelines_root: Path
    selectors: tuple[str, ...]
    full_refresh: bool
    start_time: str | None
    json_output: bool
    verbose: bool
    auto_approve: bool
    prompt_response: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_error_fragments: tuple[str, ...]
    expected_deployment_status_rows: tuple[tuple[str, ...], ...]
    expected_selected_root_names: tuple[str, ...] = ()
    expected_runtime_execution_modes: tuple[tuple[str, str | None], ...] = ()
    expected_absent_output_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CliTestCommandIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    sql_test_content: str
    expected_line_total: str
    extra_sql_test_files: tuple[tuple[str, str], ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliAuditCommandIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    project_writer_name: str
    order_items_columns: str
    order_items_order_by: str
    order_items_rows: tuple[tuple[str | None, float], ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliAuditBackfillCommandIntegrationTestCase:
    description: str
    expected_exit_code: int
    expected_quality_check_count: int
    expected_assessment: str
    expected_failing_row_count: int


@dataclass(frozen=True)
class CliPlanSnapshotIntegrationTestCase:
    description: str
    source_contents: str
    model_contents: str
    existing_table_ddl_statements: tuple[str, ...]
    expected_replay_lineage_mode: str
    expected_exit_code: int
    expected_output_fragment: str


@dataclass(frozen=True)
class CliBoundedPlanSnapshotIntegrationTestCase:
    description: str
    start_time: str
    expected_execution_mode: str
    expected_warning_count: int
    expected_catalog_load_count: int
    expected_query_count: int
    expected_point_in_time_query_count: int


@dataclass(frozen=True)
class CliTestSemanticsIntegrationTestCase:
    description: str
    sql_test_content: str
    macro_file_contents: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectPlanIntegrationTestCase:
    description: str
    expected_execution_scope: tuple[str, ...]
    expected_replay_root_models: tuple[str, ...]
    expected_initial_ownership: tuple[str, ...]
    expected_settled_ownership: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectBuildIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    late_landing_rows: tuple[tuple[str, int, int], ...]
    expected_created_relations: tuple[str, ...]
    expected_owned_relations: tuple[str, ...]
    expected_replayed_order_ids: tuple[str, ...]
    expected_final_order_ids: tuple[str, ...]
    expected_deployment_row_count: int
    expected_stable_view_count: int
    expected_replay_coverage_ranges: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class CliDirectBuildBoundaryIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    pre_capture_statements: tuple[str, ...]
    expected_boundary_keys: tuple[str, ...]
    expected_cutoff_values: tuple[str, ...]
    expected_cutoff_inclusive: tuple[bool, ...]


@dataclass(frozen=True)
class CliDirectBuildRejectionIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    rebuilt_topic: str
    expected_error_fragment: str
    expected_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectBuildGuardIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    rebuilt_topic: str
    pre_rebuild_statements: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragment: str
    expected_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class CliReciprocalOwnershipIntegrationTestCase:
    description: str
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class CliDirectBuildAuditIntegrationTestCase:
    description: str
    audit_sql_by_name: tuple[tuple[str, str], ...]
    landing_rows: tuple[tuple[str, int, int], ...]
    late_landing_rows: tuple[tuple[str, int, int], ...]
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_final_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectBuildRerunIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    restored_landing_rows: tuple[tuple[str, int, int], ...]
    late_landing_rows: tuple[tuple[str, int, int], ...]
    expected_failed_exit_code: int
    expected_incomplete_target_count: int
    expected_retention_exit_code: int
    expected_retention_error_fragment: str
    expected_rerun_exit_code: int
    expected_final_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectBuildPartialFailureIntegrationTestCase:
    description: str
    landing_rows: tuple[tuple[str, int, int], ...]
    partial_landing_rows: tuple[tuple[str, int, int], ...]
    expected_failed_exit_code: int
    expected_retention_exit_code: int
    expected_retention_error_fragment: str
    expected_partial_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectSelectedBuildIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    landing_rows: tuple[tuple[str, int, int], ...]
    boundary_landing_rows: tuple[tuple[str, int, int], ...]
    expected_order_ids: tuple[str, ...]
    expected_delta_rows: tuple[tuple[str, str], ...]
    expected_drop_statements: tuple[str, ...]
    expected_realized_relation_names: tuple[str, ...]
    expected_replay_targets: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectAggregateBuildIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    landing_rows: tuple[tuple[str, int, int], ...]
    expected_aggregate_rows: tuple[tuple[str, int], ...]
    expected_replay_targets: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectSelectedFailureIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    landing_rows: tuple[tuple[str, int, int], ...]
    expected_order_ids: tuple[str, ...]
    expected_delta_rows: tuple[tuple[str, str], ...]
    expected_failure_fragment: str
    expected_replay_targets: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectExecutionStepFailureIntegrationTestCase:
    description: str
    connection_factory: Callable[[AdapterConnection], AdapterConnection]
    expected_failure_fragment: str


@dataclass(frozen=True)
class CliDirectSelectionMatrixIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_drop_relation_names: tuple[str, ...]
    expected_replay_targets: tuple[str, ...]


@dataclass(frozen=True)
class CliDirectSelectedAuditIntegrationTestCase:
    description: str
    selectors: tuple[str, ...]
    audit_sql_by_name: tuple[tuple[str, str], ...]
    expected_query_markers: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class CliDirectAdoptedSourceIntegrationTestCase:
    description: str
    source_yml: str
    model_sql: str
    source_columns_sql: str
    initial_values_sql: str
    live_values_sql: str
    source_projection_sql: str
    expected_source_rows: tuple[tuple[str, ...], ...]
    expected_order_ids: tuple[str, ...]
    expected_replay_mode: str
    expected_replay_columns: tuple[str, str, str, str, str]


@dataclass(frozen=True)
class CliDirectAdoptedSourceFailureIntegrationTestCase:
    description: str
    source_table_name: str
    source_yml: str
    model_sql: str
    source_columns_sql: str
    expected_error_fragment: str
