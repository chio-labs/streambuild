from dataclasses import dataclass
from typing import NamedTuple

from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
)
from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayLineageMode
from streambuild.compiler.planner.types import RebuildExecutionMode
from streambuild.executor.backfill.models import BackfillExecutionResult
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


class ManagedSourceResources(NamedTuple):
    kafka_table: DesiredKafkaTable
    raw_table: DesiredTable
    materialized_view: DesiredMaterializedView


class ModelResources(NamedTuple):
    target_table: DesiredTable
    materialized_view: DesiredMaterializedView

    @property
    def target_table_name(self) -> str:
        return self.target_table.name


@dataclass(frozen=True)
class ExecuteBackfillBootstrapIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    precreate_live_landing_objects: bool
    expected_live_kafka_table_name: str
    expected_shadow_table_name: str
    expected_shadow_materialized_view_name: str
    expected_deployment_status: str
    expected_full_layout: tuple[tuple[str, str], ...]
    expected_runtime_detail_anchor_name: str = "raw__orders"
    expected_runtime_detail_strategy: str = "create_from_scratch"
    expected_runtime_detail_anchor_physical_name: str | None = None


@dataclass(frozen=True)
class ExecuteBackfillScalarReplayIntegrationTestCase:
    description: str
    replay_lineage_mode: ReplayLineageMode | str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_boundary_key: str
    expected_shadow_table_name: str
    historical_raw_rows: tuple[tuple[object, ...], ...]
    live_raw_rows: tuple[tuple[object, ...], ...]
    expected_shadow_order_ids: tuple[str, ...]
    expected_replay_written_rows: tuple[int | None, ...]


@dataclass(frozen=True)
class ExecuteBackfillOffsetReplayIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_shadow_table_name: str
    raw_rows: tuple[tuple[object, ...], ...]
    live_raw_rows: tuple[tuple[object, ...], ...]
    expected_watermark_rows: tuple[tuple[str, str], ...]
    expected_shadow_order_ids: tuple[str, ...]
    expected_replay_written_rows: tuple[int | None, ...]


@dataclass(frozen=True)
class MissingOffsetReplayCutoffIntegrationTestCase:
    description: str
    boundary_time: str
    raw_rows: tuple[tuple[object, ...], ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class MissingScalarReplayCutoffIntegrationTestCase:
    description: str
    replay_lineage_mode: ReplayLineageMode
    boundary_time: str
    raw_rows: tuple[tuple[object, ...], ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class MissingCursorStartTimeIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    start_time: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExecuteExternalSourceOffsetReplayIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_shadow_table_name: str
    source_rows: tuple[tuple[object, ...], ...]
    expected_watermark_rows: tuple[tuple[str, str], ...]
    expected_shadow_order_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExecuteExternalSourceCursorReplayIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    start_time: str | None
    expected_shadow_order_ids: tuple[str, ...]
    expected_cutoff_value: str


@dataclass(frozen=True)
class ExecuteAggregateOffsetReplayIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_shadow_table_name: str
    raw_rows: tuple[tuple[object, ...], ...]
    expected_shadow_rows: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ExecuteAggregateBoundedOffsetReplayIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    lower_bound_source_order_id: str
    lower_bound_offset_millis: int
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, int], ...]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ResolveAggregateUnsupportedReplayBehaviorIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    lower_bound_source_order_id: str
    lower_bound_offset_millis: int
    bounded_replay_fallback: BoundedReplayFallback | str
    expected_execution_mode: RebuildExecutionMode


@dataclass(frozen=True)
class ExecuteSeededBoundedScalarReplayIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteSeededBoundedOffsetReplayIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteUnseededBoundedScalarReplayIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteUnseededBoundedOffsetReplayIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteBoundedPreservationMatrixIntegrationTestCase:
    description: str
    source_ownership: str
    replay_lineage_mode: ReplayLineageMode
    requested_execution_mode: RebuildExecutionMode
    expected_execution_mode: RebuildExecutionMode
    expected_shadow_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteMultipleBackfillsIntegrationTestCase:
    description: str
    first_deployment_id: str
    second_deployment_id: str
    created_at: str
    boundary_time: str
    expected_staged_table_names: tuple[str, ...]


@dataclass(frozen=True)
class ExecuteBoundedReplayReportingIntegrationTestCase:
    description: str
    first_deployment_id: str
    second_deployment_id: str
    created_at: str
    boundary_time: str
    expected_first_strategy: str
    expected_second_strategy: str
    expected_active_deployment_id: str


@dataclass(frozen=True)
class ExecuteRepeatedPublishedBackfillIntegrationTestCase:
    description: str
    first_deployment_id: str
    second_deployment_id: str
    created_at: str
    first_boundary_time: str
    second_boundary_time: str
    expected_raw_view_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class BackfillAfterDeletedStagedTableIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_recreated_relation_name: str


@dataclass(frozen=True)
class PersistWatermarksWithoutMetadataTableIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_watermark_table_count: int


@dataclass(frozen=True)
class ExecuteMixedRootBackfillReportingIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_report_rows: tuple[tuple[str, str, str | None], ...]


@dataclass(frozen=True)
class ExecuteReferenceJoinBackfillIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_region_lookup_shadow_name: str
    expected_enriched_shadow_name: str
    expected_enriched_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecutePublishedReferenceJoinBackfillIntegrationTestCase:
    description: str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    boundary_time: str
    expected_enriched_shadow_name: str
    expected_enriched_rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ExecuteStartTimeReplayIntegrationTestCase:
    description: str
    replay_lineage_mode: ReplayLineageMode | str
    initial_deployment_id: str
    changed_deployment_id: str
    created_at: str
    initial_boundary_time: str
    changed_boundary_time: str
    lower_bound_source_order_id: str
    lower_bound_offset_millis: int
    expected_shadow_table_name: str
    expected_shadow_rows: tuple[tuple[str, str], ...]


class StartTimeReplayScenarioResult(NamedTuple):
    connection_settings: ClickHouseConnectionSettings
    database: str
    compiled_pipeline: CompiledPipeline
    start_time_result: BackfillExecutionResult
    converted_start_time: str
    shadow_rows: tuple[tuple[str, str], ...]


class BoundedPreservationMatrixScenarioResult(NamedTuple):
    execution_mode: RebuildExecutionMode
    shadow_rows: tuple[tuple[str, str], ...]
