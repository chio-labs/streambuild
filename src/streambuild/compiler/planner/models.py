"""Planner runtime models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.planner.types import (
    DeploymentAction,
    DeploymentPhase,
    PlannedChangeType,
    RebuildExecutionMode,
    RebuildStrategy,
    SchemaChangeBackfillMode,
    TableSchemaChangeKind,
    TableSchemaSeedCompatibility,
)
from streambuild.compiler.shared.models import ObjectKey
from streambuild.spec.models.types import BoundedReplayFallback


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
    configured_backfill_mode: SchemaChangeBackfillMode | str | None = None
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
                SchemaChangeBackfillMode(self.configured_backfill_mode),
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
