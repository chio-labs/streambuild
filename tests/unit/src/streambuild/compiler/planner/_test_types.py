from dataclasses import dataclass

from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    ReplayOnChangePolicy,
)
from streambuild.compiler.discovery.types import (
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
    ReplayOnChangeMode,
)
from streambuild.compiler.planner.types import (
    DeploymentAction,
    PlannedChangeType,
    RebuildExecutionMode,
    RebuildStrategy,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)


@dataclass(frozen=True)
class InspectRootDeploymentStateTestCase:
    description: str
    active_bindings: tuple[tuple[str, str], ...]
    physical_candidates: tuple[tuple[str, str], ...]
    expected_state_kind: str
    expected_active_deployment_id: str | None


@dataclass(frozen=True)
class PlanningSnapshotAssemblyTestCase:
    description: str
    expected_catalog_load_count: int
    expected_query_count: int


@dataclass(frozen=True)
class PlanningSnapshotCapabilityTestCase:
    description: str
    expected_error_message: str
    expected_catalog_load_count: int
    expected_query_count: int


@dataclass(frozen=True)
class BuildActualStateTestCase:
    description: str
    expected_ordered_keys: tuple[tuple[str | None, str, str], ...]
    expected_first_table_settings: dict[str, str] | None
    expected_first_mv_source_table_name: str
    expected_first_kafka_consumer_group: str


@dataclass(frozen=True)
class ActualStateRowNormalizationTestCase:
    description: str
    raw_engine: str
    raw_sorting_key: str
    raw_default_expression: object
    raw_partition_key: object
    expected_engine: str
    expected_order_by: tuple[str, ...]
    expected_default_expression: str | None
    expected_partition_key: str | None


@dataclass(frozen=True)
class ActualStateProjectionTestCase:
    description: str
    expected_kafka_columns: tuple[tuple[str, str, str | None], ...]
    expected_kafka_broker_list: str
    expected_kafka_topic: str
    expected_kafka_consumer_group: str
    expected_kafka_format: str
    expected_kafka_settings: dict[str, str] | None
    expected_raw_columns: tuple[tuple[str, str, str | None], ...]
    expected_raw_engine: str
    expected_raw_order_by: tuple[str, ...]
    expected_raw_partition_by: str | None
    expected_raw_ttl: str | None
    expected_raw_settings: dict[str, str] | None
    expected_landing_mv_source: str
    expected_landing_mv_target: str
    expected_landing_mv_query: str
    expected_transform_columns: tuple[tuple[str, str, str | None], ...]
    expected_transform_engine: str
    expected_transform_order_by: tuple[str, ...]
    expected_transform_partition_by: str | None
    expected_transform_ttl: str | None
    expected_transform_settings: dict[str, str] | None


@dataclass(frozen=True)
class PreservedCatalogProjectionTestCase:
    description: str
    expected_ttl: str | None
    expected_settings: dict[str, str] | None


@dataclass(frozen=True)
class PlannerRebuildSubtreeTestCase:
    description: str
    root_key: tuple[str | None, str, str]
    expected_descendant_keys: tuple[tuple[str | None, str, str], ...]
    expected_upstream_boundary_key: tuple[str | None, str, str]
    expected_strategy: RebuildStrategy
    expected_execution_mode: RebuildExecutionMode = RebuildExecutionMode.FULL_REBUILD


@dataclass(frozen=True)
class PlannerReplayAnchorSelectionTestCase:
    description: str
    query: str
    expected_upstream_boundary_key: tuple[str | None, str, str]
    replay_lineage_mode: ReplayLineageMode | str = ReplayLineageMode.OFFSETS
    replay_anchor: ReplayAnchorMode | str = ReplayAnchorMode.AUTO
    order_by: tuple[str, ...] = ("order_id",)


@dataclass(frozen=True)
class PlannerMutableWarningTestCase:
    description: str
    expected_warning_code: str
    expected_target_key: tuple[str | None, str, str]


@dataclass(frozen=True)
class PlannerObjectChangeTestCase:
    description: str
    expected_changes: tuple[tuple[tuple[str | None, str, str], str], ...]


@dataclass(frozen=True)
class PlannerCollapseSubtreesTestCase:
    description: str
    changed_keys: tuple[tuple[str | None, str, str], ...]
    change_types: tuple[PlannedChangeType, ...]
    expected_root_keys: tuple[tuple[str | None, str, str], ...]


@dataclass(frozen=True)
class PlannerDeploymentPlanTestCase:
    description: str
    expected_change_count: int
    expected_rebuild_root_keys: tuple[tuple[str | None, str, str], ...]
    expected_steps: tuple[tuple[str, str, tuple[str | None, str, str] | None], ...]


@dataclass(frozen=True)
class PlannerFullRefreshPlanTestCase:
    description: str
    full_refresh_key: tuple[str | None, str, str]
    expected_rebuild_root_keys: tuple[tuple[str | None, str, str], ...]
    expected_execution_mode: RebuildExecutionMode


@dataclass(frozen=True)
class PlannerShadowIdentityTestCase:
    description: str
    deployment_id: str
    expected_prepared_shadow_objects: tuple[tuple[tuple[str | None, str, str], str], ...]
    expected_plan_step_physical_names: tuple[str, ...]


@dataclass(frozen=True)
class PlannerPreservationMatrixTestCase:
    description: str
    source_ownership: str
    replay_lineage_mode: ReplayLineageMode
    expected_source_type: type[KafkaLandingStep] | type[ExternalTableSourceStep]
    expected_desired_object_count: int
    expected_external_replay_boundary_modes: tuple[ReplayBoundaryMode, ...]
    expected_upstream_boundary_key: tuple[str | None, str, str]
    expected_actions: tuple[DeploymentAction, ...]


@dataclass(frozen=True)
class PlannerTableSchemaClassificationTestCase:
    description: str
    actual_columns: tuple[tuple[str, str], ...]
    desired_columns: tuple[tuple[str, str], ...]
    expected_schema_change_kind: TableSchemaChangeKind | None
    expected_seed_compatibility: TableSchemaSeedCompatibility | None
    expected_change_type: PlannedChangeType = PlannedChangeType.REBUILD


@dataclass(frozen=True)
class BuildMetadataStateTestCase:
    description: str
    expected_object_state_keys: tuple[tuple[str | None, str, str], ...]
    expected_deployment_ids: tuple[str, ...]
    expected_first_deployment_root_keys: tuple[tuple[str | None, str, str], ...]
    expected_first_deployment_warning_codes: tuple[str, ...]
    expected_first_deployment_mapping_names: tuple[str, ...]
    expected_watermark_boundary_keys: tuple[str, ...]
    expected_runtime_detail_target_names: tuple[str, ...]


@dataclass(frozen=True)
class PlannerExecutionModeTestCase:
    description: str
    schema_change_kind: TableSchemaChangeKind | str | None
    seed_compatibility: TableSchemaSeedCompatibility | str | None
    expected_execution_mode: RebuildExecutionMode
    configured_backfill_mode: ReplayOnChangeMode | str | None = None
    configured_lookback_seconds: int | None = None
    replay_on_change: ReplayOnChangePolicy | None = None


@dataclass(frozen=True)
class DeploymentPhysicalNameRecognitionTestCase:
    description: str
    physical_name: str
    expected_is_deployment_name: bool


@dataclass(frozen=True)
class DeploymentPhysicalNameParsingTestCase:
    description: str
    physical_name: str
    expected_logical_name: str
    expected_deployment_id: str
