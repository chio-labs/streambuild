from dataclasses import dataclass

from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayLineageMode
from streambuild.compiler.planner.types import RebuildExecutionMode


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
    expected_error_fragment: str


@dataclass(frozen=True)
class PersistWatermarksWithoutMetadataTableIntegrationTestCase:
    description: str
    deployment_id: str
    created_at: str
    boundary_time: str
    expected_error_fragment: str


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
