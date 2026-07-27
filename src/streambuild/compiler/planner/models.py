"""Planner runtime models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.compile.models import (
    Column,
    KafkaSettings,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayLineageMode,
    ReplayOnChangeMode,
)
from streambuild.compiler.planner.types import (
    DeploymentAction,
    DeploymentPhase,
    PlannedChangeType,
    RebuildExecutionMode,
    RebuildStrategy,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)


@dataclass(frozen=True)
class PlanningWarehouseSnapshot:
    """Immutable live catalog and persisted state captured for one plan."""

    catalog: CatalogSnapshot
    object_state_records: tuple[ObjectStateRecord, ...]


@dataclass(frozen=True)
class ActualKafkaTable:
    """A normalized actual Kafka engine table."""

    key: ObjectKey
    spec: KafkaTableSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def kafka(self) -> KafkaSettings:
        return self.spec.kafka


@dataclass(frozen=True)
class ActualTable:
    """A normalized actual managed ClickHouse table."""

    key: ObjectKey
    spec: TableSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def engine(self) -> str:
        return self.spec.storage.engine

    @property
    def order_by(self) -> tuple[str, ...]:
        return self.spec.storage.order_by

    @property
    def partition_by(self) -> str | None:
        return self.spec.storage.partition_by

    @property
    def ttl(self) -> str | None:
        return self.spec.storage.ttl

    @property
    def settings(self) -> Mapping[str, str] | None:
        return self.spec.storage.settings


@dataclass(frozen=True)
class ActualMaterializedView:
    """A normalized actual materialized view."""

    key: ObjectKey
    spec: MaterializedViewSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def source_table_name(self) -> str:
        return self.spec.source_table_name

    @property
    def target_table_name(self) -> str:
        return self.spec.target_table_name

    @property
    def query(self) -> str:
        return self.spec.query


@dataclass(frozen=True)
class ActualState:
    """Project-level flat actual object graph."""

    objects: tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...]


@dataclass(frozen=True)
class RootDeploymentInspection:
    """Inspection result for one managed root logical table."""

    root_key: ObjectKey
    state_kind: str
    active_deployment_id: str | None


@dataclass(frozen=True)
class ActualStateInspection:
    """Live and persisted inputs needed to assemble actual state."""

    existing_names: frozenset[str]
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection]
    object_state_by_deployment_and_key: dict[tuple[str, ObjectKey], ObjectStateRecord]
    latest_object_state_by_key: dict[ObjectKey, ObjectStateRecord]
    active_physical_names_by_logical_name: dict[str, str]
    active_table_specs_by_name: dict[str, TableSpec]


@dataclass(frozen=True)
class ObjectStateMetadataRow:
    """Row shape for persisted object-state metadata."""

    deployment_id: str
    database_name: str | None
    object_type: str
    object_name: str
    normalized_fingerprint: str
    normalized_query: str | None
    recorded_at: str


@dataclass(frozen=True)
class TableNameSystemRow:
    """Row shape for system table name lookups."""

    name: str


@dataclass(frozen=True)
class TableColumnSystemRow:
    """Row shape for system column inspection."""

    table_name: str
    name: str
    type: str
    default_expression: str | None


@dataclass(frozen=True)
class TableStorageSystemRow:
    """Row shape for system table storage inspection."""

    table_name: str
    engine: str
    sorting_key: str
    partition_key: str | None


@dataclass(frozen=True)
class PlannedObjectChange:
    """A planner-local object change classification."""

    key: ObjectKey
    change_type: PlannedChangeType | str
    force_full_refresh: bool = False
    forced_start_time: str | None = None
    schema_change_kind: TableSchemaChangeKind | str | None = None
    seed_compatibility: TableSchemaSeedCompatibility | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "change_type", PlannedChangeType(self.change_type))
        if self.schema_change_kind is not None:
            object.__setattr__(
                self,
                "schema_change_kind",
                TableSchemaChangeKind(self.schema_change_kind),
            )
        if self.seed_compatibility is not None:
            object.__setattr__(
                self,
                "seed_compatibility",
                TableSchemaSeedCompatibility(self.seed_compatibility),
            )


@dataclass(frozen=True)
class PlannedSqlDiff:
    """A unified SQL diff for one changed planned object."""

    key: ObjectKey
    object_type: str
    name: str
    diff_lines: tuple[str, ...]


@dataclass(frozen=True)
class RebuildSubtree:
    """A transitive desired-object rebuild subtree."""

    root_key: ObjectKey
    affected_keys: tuple[ObjectKey, ...]
    upstream_boundary_key: ObjectKey
    strategy: RebuildStrategy | str
    execution_mode: RebuildExecutionMode | str = RebuildExecutionMode.FULL_REBUILD
    forced_full_refresh: bool = False
    forced_start_time: str | None = None
    requested_start_time: str | None = None
    configured_backfill_mode: ReplayOnChangeMode | str | None = None
    execution_lookback_seconds: int | None = None
    history_preserving_bounded_supported: bool = True
    resolved_bounded_replay_fallback: BoundedReplayFallback | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy", RebuildStrategy(self.strategy))
        object.__setattr__(self, "execution_mode", RebuildExecutionMode(self.execution_mode))
        if self.configured_backfill_mode is not None:
            object.__setattr__(
                self,
                "configured_backfill_mode",
                ReplayOnChangeMode(self.configured_backfill_mode),
            )
        if self.resolved_bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "resolved_bounded_replay_fallback",
                BoundedReplayFallback(self.resolved_bounded_replay_fallback),
            )


@dataclass(frozen=True)
class DeploymentStep:
    """A staged deployment step for a rebuild plan."""

    step_id: str
    phase: DeploymentPhase | str
    action: DeploymentAction | str
    root_key: ObjectKey
    target_key: ObjectKey | None = None
    physical_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", DeploymentPhase(self.phase))
        object.__setattr__(self, "action", DeploymentAction(self.action))


@dataclass(frozen=True)
class PreparedShadowObject:
    """A deterministic physical shadow-object identity for a logical object."""

    logical_key: ObjectKey
    physical_name: str


@dataclass(frozen=True)
class PlannerWarning:
    """A planner-visible warning about rollout semantics."""

    warning_code: str
    message: str
    root_key: ObjectKey
    target_key: ObjectKey | None = None


@dataclass(frozen=True)
class DeploymentPlan:
    """A conservative staged deployment plan."""

    deployment_id: str | None
    object_changes: tuple[PlannedObjectChange, ...]
    rebuild_subtrees: tuple[RebuildSubtree, ...]
    steps: tuple[DeploymentStep, ...]
    prepared_shadow_objects: tuple[PreparedShadowObject, ...]
    warnings: tuple[PlannerWarning, ...]
    sql_diffs: tuple[PlannedSqlDiff, ...] = ()


@dataclass(frozen=True)
class PreparedObjectMapping:
    """A logical-to-physical prepared object mapping for a deployment."""

    logical_key: ObjectKey
    physical_name: str


@dataclass(frozen=True)
class ObjectStateRecord:
    """Framework-owned applied state for a logical object."""

    deployment_id: str
    key: ObjectKey
    normalized_fingerprint: str
    normalized_query: str | None
    recorded_at: str


@dataclass(frozen=True)
class DeploymentRecord:
    """Stored staged deployment metadata."""

    deployment_id: str
    created_at: str
    status: str
    replay_lineage_mode: ReplayLineageMode | str
    selected_root_keys: tuple[ObjectKey, ...]
    warning_codes: tuple[str, ...]
    prepared_object_mappings: tuple[PreparedObjectMapping, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))


@dataclass(frozen=True)
class DeploymentWatermarkRecord:
    """Stored replay-boundary or progress metadata for a deployment."""

    deployment_id: str
    root_key: ObjectKey
    anchor_key: ObjectKey
    boundary_key: str
    cutoff_value: str


@dataclass(frozen=True)
class DeploymentRuntimeDetailRecord:
    """Stored per-root runtime decision metadata for a deployment."""

    deployment_id: str
    root_key: ObjectKey
    state_kind: str
    replay_strategy: str
    active_deployment_id: str | None
    anchor_key: ObjectKey
    anchor_physical_name: str | None
    execution_mode: str | None
    configured_backfill_mode: str | None
    execution_lookback_seconds: int | None
    live_target_names: tuple[str, ...]


@dataclass(frozen=True)
class PublishEventRecord:
    """Stored publish/activation history for one deployment."""

    deployment_id: str
    published_at: str
    logical_view_names: tuple[str, ...]


@dataclass(frozen=True)
class MetadataState:
    """Project-level stored metadata-state records."""

    object_states: tuple[ObjectStateRecord, ...]
    deployments: tuple[DeploymentRecord, ...]
    deployment_watermarks: tuple[DeploymentWatermarkRecord, ...]
    deployment_runtime_details: tuple[DeploymentRuntimeDetailRecord, ...]
    publish_events: tuple[PublishEventRecord, ...]
