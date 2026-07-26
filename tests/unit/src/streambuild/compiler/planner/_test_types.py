from dataclasses import dataclass

from streambuild.compiler.compile.models import CompiledExternalSource, CompiledManagedSource
from streambuild.compiler.discovery.models import SchemaChangeBackfillPolicy
from streambuild.compiler.discovery.types import (
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
)
from streambuild.compiler.planner.types import (
    DeploymentAction,
    PlannedChangeType,
    RebuildExecutionMode,
    RebuildStrategy,
    SchemaChangeBackfillMode,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)


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
    expected_source_type: type[CompiledManagedSource] | type[CompiledExternalSource]
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
class PlannerExecutionModeTestCase:
    description: str
    schema_change_kind: TableSchemaChangeKind | str | None
    seed_compatibility: TableSchemaSeedCompatibility | str | None
    expected_execution_mode: RebuildExecutionMode
    configured_backfill_mode: SchemaChangeBackfillMode | str | None = None
    configured_lookback_seconds: int | None = None
    schema_change_backfill: SchemaChangeBackfillPolicy | None = None


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
