"""Conservative rebuild subtree selection helpers."""

from __future__ import annotations

from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.compiler.planner._helpers.graph import (
    descendant_keys,
    nearest_upstream_replay_anchor_key,
)
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_CREATE,
    PLANNED_CHANGE_TYPE_REBUILD,
    REBUILD_EXECUTION_MODE_FULL,
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
    REBUILD_STRATEGY_SHADOW,
    TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING,
    TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE,
)
from streambuild.compiler.planner.models import PlannedObjectChange, RebuildSubtree
from streambuild.compiler.planner.types import (
    RebuildExecutionMode,
    SchemaChangeBackfillMode,
)
from streambuild.spec.models import SchemaChangeBackfillRule


def build_rebuild_subtree(
    *,
    desired_state: DesiredState,
    root_key: ObjectKey,
    execution_mode: RebuildExecutionMode = REBUILD_EXECUTION_MODE_FULL,
    forced_full_refresh: bool = False,
    forced_start_time: str | None = None,
    configured_backfill_mode: SchemaChangeBackfillMode | None = None,
    execution_lookback_seconds: int | None = None,
) -> RebuildSubtree:
    """Build a conservative rebuild subtree from a changed desired object key."""

    return RebuildSubtree(
        root_key=root_key,
        affected_keys=descendant_keys(desired_state=desired_state, root_key=root_key),
        upstream_boundary_key=nearest_upstream_replay_anchor_key(
            desired_state=desired_state,
            root_key=root_key,
            allow_root_key=False,
        ),
        strategy=REBUILD_STRATEGY_SHADOW,
        execution_mode=execution_mode,
        forced_full_refresh=forced_full_refresh,
        forced_start_time=forced_start_time,
        configured_backfill_mode=configured_backfill_mode,
        execution_lookback_seconds=execution_lookback_seconds,
    )


def emit_rebuild_subtrees_from_changes(
    *,
    desired_state: DesiredState,
    object_changes: tuple[PlannedObjectChange, ...],
) -> tuple[RebuildSubtree, ...]:
    """Build rebuild subtrees while collapsing descendant candidate roots."""

    desired_tables_by_key: dict[ObjectKey, DesiredTable] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    candidate_subtrees: tuple[RebuildSubtree, ...] = tuple(
        _build_rebuild_subtree_for_change(
            desired_state=desired_state,
            object_change=object_change,
            desired_table=desired_tables_by_key.get(object_change.key),
        )
        for object_change in object_changes
        if object_change.change_type in {PLANNED_CHANGE_TYPE_CREATE, PLANNED_CHANGE_TYPE_REBUILD}
        and object_change.key.object_type != DESIRED_OBJECT_TYPE_KAFKA_TABLE
        and not _is_stable_landing_object(desired_state=desired_state, key=object_change.key)
    )
    sorted_candidate_subtrees: tuple[RebuildSubtree, ...] = tuple(
        sorted(
            candidate_subtrees,
            key=lambda subtree: (
                -len(subtree.affected_keys),
                subtree.root_key.object_type,
                subtree.root_key.name,
            ),
        )
    )
    retained_subtrees: list[RebuildSubtree] = []
    subtree: RebuildSubtree
    for subtree in sorted_candidate_subtrees:
        if any(
            subtree.root_key in retained_subtree.affected_keys
            for retained_subtree in retained_subtrees
        ):
            continue
        retained_subtrees.append(subtree)

    return tuple(retained_subtrees)


def _is_stable_landing_object(*, desired_state: DesiredState, key: ObjectKey) -> bool:
    if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name.startswith(RAW_TABLE_NAME_PREFIX):
        return True
    if key.object_type != DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW:
        return False
    object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, (DesiredTable, DesiredMaterializedView))
    }
    object_: DesiredTable | DesiredMaterializedView | None = object_by_key.get(key)
    return isinstance(object_, DesiredMaterializedView) and object_.target_table_name.startswith(
        RAW_TABLE_NAME_PREFIX
    )


def _default_execution_mode_for_change(object_change: PlannedObjectChange) -> RebuildExecutionMode:
    if (
        object_change.schema_change_kind == TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING
        and object_change.seed_compatibility == TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE
    ):
        return REBUILD_EXECUTION_MODE_SEEDED_BOUNDED
    return REBUILD_EXECUTION_MODE_FULL


def _build_rebuild_subtree_for_change(
    *,
    desired_state: DesiredState,
    object_change: PlannedObjectChange,
    desired_table: DesiredTable | None,
) -> RebuildSubtree:
    if object_change.force_full_refresh:
        return build_rebuild_subtree(
            desired_state=desired_state,
            root_key=object_change.key,
            execution_mode=REBUILD_EXECUTION_MODE_FULL,
            forced_full_refresh=True,
            configured_backfill_mode=SchemaChangeBackfillMode(SchemaChangeBackfillMode.FULL),
            execution_lookback_seconds=None,
        )
    if object_change.forced_start_time is not None:
        return build_rebuild_subtree(
            desired_state=desired_state,
            root_key=object_change.key,
            execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
            forced_start_time=object_change.forced_start_time,
            configured_backfill_mode=None,
            execution_lookback_seconds=None,
        )
    resolved_execution_mode, configured_backfill_mode, execution_lookback_seconds = (
        _resolve_execution_policy(
            object_change=object_change,
            desired_table=desired_table,
        )
    )
    return build_rebuild_subtree(
        desired_state=desired_state,
        root_key=object_change.key,
        execution_mode=resolved_execution_mode,
        configured_backfill_mode=configured_backfill_mode,
        execution_lookback_seconds=execution_lookback_seconds,
    )


def _resolve_execution_policy(
    *,
    object_change: PlannedObjectChange,
    desired_table: DesiredTable | None,
) -> tuple[RebuildExecutionMode, SchemaChangeBackfillMode | None, int | None]:
    if desired_table is None or desired_table.schema_change_backfill is None:
        return (_default_execution_mode_for_change(object_change), None, None)
    if object_change.schema_change_kind == TABLE_SCHEMA_CHANGE_KIND_NON_BREAKING:
        policy_rule: SchemaChangeBackfillRule | None = (
            desired_table.schema_change_backfill.non_breaking
        )
    else:
        policy_rule = desired_table.schema_change_backfill.breaking
    if policy_rule is None:
        return (_default_execution_mode_for_change(object_change), None, None)
    if policy_rule.mode == SchemaChangeBackfillMode.FULL:
        return (
            REBUILD_EXECUTION_MODE_FULL,
            SchemaChangeBackfillMode(SchemaChangeBackfillMode.FULL),
            None,
        )
    if object_change.seed_compatibility == TABLE_SCHEMA_SEED_COMPATIBILITY_SEEDABLE:
        return (
            REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
            SchemaChangeBackfillMode(SchemaChangeBackfillMode.BOUNDED),
            policy_rule.lookback_seconds,
        )
    return (
        REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
        SchemaChangeBackfillMode(SchemaChangeBackfillMode.BOUNDED),
        policy_rule.lookback_seconds,
    )
