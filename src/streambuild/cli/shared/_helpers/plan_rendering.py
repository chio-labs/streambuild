"""Plan rendering helpers for CLI plan output."""

from __future__ import annotations

from streambuild.cli.shared.main._cli_style import cli_style
from streambuild.cli.shared.models import CompactChangedTargetSummary
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_CREATE,
    PLANNED_CHANGE_TYPE_NO_OP,
    PLANNED_CHANGE_TYPE_REBUILD,
    PLANNED_CHANGE_TYPE_REPLACE,
    REBUILD_EXECUTION_MODE_FULL,
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
)
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    PlannedObjectChange,
    PlannedSqlDiff,
    RebuildSubtree,
)
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.models import DesiredMaterializedView, DesiredTable, ObjectKey
from streambuild.spec.types import BoundedReplayFallback, SchemaChangeBackfillMode


def object_key_payload(key: ObjectKey) -> dict[str, str | None]:
    return {
        "database": key.database,
        "object_type": key.object_type,
        "name": key.name,
    }


def render_subtree_diagram(
    *,
    subtree: RebuildSubtree,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    live_targets: tuple[str, ...] = live_target_names(
        subtree=subtree,
        desired_object_by_key=desired_object_by_key,
    )
    lines: list[str] = [f"[replay start] {subtree.upstream_boundary_key.name}"]
    if not live_targets:
        lines.append(f"└── [live target] {subtree.root_key.name}")
        return lines
    live_target_name: str
    for index, live_target_name in enumerate(live_targets):
        branch: str = "└──" if index == len(live_targets) - 1 else "├──"
        lines.append(f"{branch} [live target] {live_target_name}")
    return lines


def live_target_names(
    *,
    subtree: RebuildSubtree,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    live_targets: tuple[str, ...] = tuple(
        sorted(
            key.name
            for key in subtree.affected_keys
            if key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        )
    )
    if live_targets:
        return live_targets
    desired_object: DesiredTable | DesiredMaterializedView | None = desired_object_by_key.get(
        subtree.root_key
    )
    if isinstance(
        desired_object, DesiredMaterializedView
    ) and desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
        return (desired_object.target_table_name,)
    if (
        subtree.root_key.object_type == DESIRED_OBJECT_TYPE_TABLE
        and subtree.root_key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    ):
        return (subtree.root_key.name,)
    return ()


def render_sql_diff_plan_context(
    *,
    sql_diff: PlannedSqlDiff,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    subtree: RebuildSubtree | None = subtree_for_key(
        rebuild_subtrees=plan.rebuild_subtrees, key=sql_diff.key
    )
    if subtree is None:
        return []
    lines: list[str] = []
    live_targets: tuple[str, ...] = live_target_names(
        subtree=subtree,
        desired_object_by_key=desired_object_by_key,
    )
    if live_targets:
        live_target_label: str = ", ".join(live_targets)
        if sql_diff.object_type == DESIRED_OBJECT_TYPE_TABLE and sql_diff.name in live_targets:
            lines.append(cli_style().label_value(label="Live target", value=live_target_label))
        else:
            lines.append(
                cli_style().label_value(label="Affects live target", value=live_target_label)
            )

    schema_change: PlannedObjectChange | None = schema_change_for_subtree(
        subtree=subtree,
        object_changes=plan.object_changes,
    )
    if sql_diff.object_type == DESIRED_OBJECT_TYPE_TABLE and schema_change is not None:
        if subtree.configured_backfill_mode is not None:
            lines.append(
                cli_style().label_value(
                    label="Schema-change backfill", value=format_backfill_policy(subtree)
                )
            )
        lines.append(
            cli_style().label_value(label="Plan", value=describe_subtree_rebuild_behavior(subtree))
        )
    return lines


def subtree_for_key(
    *, rebuild_subtrees: tuple[RebuildSubtree, ...], key: ObjectKey
) -> RebuildSubtree | None:
    subtree: RebuildSubtree
    for subtree in rebuild_subtrees:
        if key == subtree.root_key or key in subtree.affected_keys:
            return subtree
    return None


def schema_change_for_subtree(
    *,
    subtree: RebuildSubtree,
    object_changes: tuple[PlannedObjectChange, ...],
) -> PlannedObjectChange | None:
    schema_changes: list[PlannedObjectChange] = [
        object_change
        for object_change in object_changes
        if object_change.key in subtree.affected_keys
        and object_change.schema_change_kind is not None
    ]
    if not schema_changes:
        return None
    live_target_change: PlannedObjectChange | None = next(
        (
            object_change
            for object_change in schema_changes
            if object_change.key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and object_change.key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        ),
        None,
    )
    if live_target_change is not None:
        return live_target_change
    return schema_changes[0]


def diff_target_names(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    target_names: list[str] = []
    sql_diff: PlannedSqlDiff
    for sql_diff in plan.sql_diffs:
        subtree: RebuildSubtree | None = subtree_for_key(
            rebuild_subtrees=plan.rebuild_subtrees, key=sql_diff.key
        )
        if subtree is None:
            target_names.append(sql_diff.name)
            continue
        live_targets: tuple[str, ...] = live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        )
        target_names.extend(live_targets or (sql_diff.name,))
    return tuple(dict.fromkeys(target_names))


def new_target_names_for_subtree(
    *,
    subtree: RebuildSubtree,
    object_changes: tuple[PlannedObjectChange, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            object_change.key.name
            for object_change in object_changes
            if object_change.key in subtree.affected_keys
            and object_change.key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and object_change.schema_change_kind is None
            and object_change.change_type
            in {PLANNED_CHANGE_TYPE_CREATE, PLANNED_CHANGE_TYPE_REPLACE}
        )
    )


def new_target_names(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    new_target_names: list[str] = []
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        subtree_new_target_names: tuple[str, ...] = new_target_names_for_subtree(
            subtree=subtree,
            object_changes=plan.object_changes,
        )
        if subtree_new_target_names:
            new_target_names.extend(subtree_new_target_names)
            continue
        live_target_name: str
        for live_target_name in live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            if target_is_new(
                target_name=live_target_name,
                subtree=subtree,
                object_changes=plan.object_changes,
            ):
                new_target_names.append(live_target_name)
    return tuple(dict.fromkeys(new_target_names))


def target_is_new(
    *,
    target_name: str,
    subtree: RebuildSubtree,
    object_changes: tuple[PlannedObjectChange, ...],
) -> bool:
    object_change: PlannedObjectChange
    for object_change in object_changes:
        if (
            object_change.key in subtree.affected_keys
            and object_change.key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and object_change.key.name == target_name
            and object_change.change_type
            in {PLANNED_CHANGE_TYPE_CREATE, PLANNED_CHANGE_TYPE_REPLACE}
            and object_change.schema_change_kind is None
        ):
            return True
    return False


def compact_changed_target_summaries(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[CompactChangedTargetSummary, ...]:
    detail_lines_by_target_name: dict[str, list[str]] = {}
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        live_target_name: str
        for live_target_name in live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            if target_is_new(
                target_name=live_target_name,
                subtree=subtree,
                object_changes=plan.object_changes,
            ):
                continue
            detail_lines: tuple[str, ...] = compact_changed_target_detail_lines(
                target_name=live_target_name,
                subtree=subtree,
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
            if detail_lines:
                detail_lines_by_target_name.setdefault(live_target_name, []).extend(detail_lines)
    return tuple(
        CompactChangedTargetSummary(
            target_name=target_name,
            detail_lines=tuple(dict.fromkeys(detail_lines_by_target_name[target_name])),
        )
        for target_name in detail_lines_by_target_name
    )


def compact_changed_target_detail_lines(
    *,
    target_name: str,
    subtree: RebuildSubtree,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    detail_lines: list[str] = []
    object_change: PlannedObjectChange
    for object_change in plan.object_changes:
        if (
            object_change.key not in subtree.affected_keys
            or object_change.change_type == PLANNED_CHANGE_TYPE_NO_OP
        ):
            continue
        desired_object: DesiredTable | DesiredMaterializedView | None = desired_object_by_key.get(
            object_change.key
        )
        if (
            isinstance(desired_object, DesiredMaterializedView)
            and desired_object.target_table_name == target_name
            and object_change.schema_change_kind is None
        ):
            detail_lines.append("transform query changed")
            continue
        if (
            object_change.key.object_type == DESIRED_OBJECT_TYPE_TABLE
            and object_change.key.name == target_name
        ):
            if object_change.force_full_refresh:
                detail_lines.append("full refresh requested")
                detail_lines.append(f"plan: {describe_subtree_rebuild_behavior(subtree)}")
                continue
            requested_start_time: str | None = (
                subtree.requested_start_time or object_change.forced_start_time
            )
            if requested_start_time is not None:
                detail_lines.append(f"start time requested: {requested_start_time}")
                detail_lines.extend(unsupported_replay_detail_lines(subtree))
                detail_lines.append(f"plan: {describe_subtree_rebuild_behavior(subtree)}")
                continue
            if object_change.schema_change_kind is not None:
                detail_lines.append("table schema changed")
                if subtree.configured_backfill_mode is not None:
                    detail_lines.append(
                        f"schema-change backfill: {format_backfill_policy(subtree)}"
                    )
                detail_lines.extend(unsupported_replay_detail_lines(subtree))
                detail_lines.append(f"plan: {describe_subtree_rebuild_behavior(subtree)}")
                continue
            if object_change.change_type in {
                PLANNED_CHANGE_TYPE_REPLACE,
                PLANNED_CHANGE_TYPE_REBUILD,
            }:
                detail_lines.append("table definition changed")
    return tuple(dict.fromkeys(detail_lines))


def rollout_object_entries(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[tuple[str, str], ...]:
    rollout_objects: list[tuple[str, str]] = []
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        rollout_objects.append(("replay source", subtree.upstream_boundary_key.name))
        desired_object: DesiredTable | DesiredMaterializedView | None = desired_object_by_key.get(
            subtree.root_key
        )
        if isinstance(desired_object, DesiredMaterializedView):
            rollout_objects.append(("transform", desired_object.name))
        live_target_name: str
        for live_target_name in live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            rollout_objects.append(("live target", live_target_name))

    return tuple(dict.fromkeys(rollout_objects))


def changed_object_entries(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[tuple[str, str], ...]:
    changed_entries: list[tuple[str, str]] = []
    object_change: PlannedObjectChange
    for object_change in plan.object_changes:
        if object_change.change_type == PLANNED_CHANGE_TYPE_NO_OP:
            continue
        desired_object: DesiredTable | DesiredMaterializedView | None = desired_object_by_key.get(
            object_change.key
        )
        if isinstance(
            desired_object, DesiredMaterializedView
        ) and desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            changed_entries.append(("transform", desired_object.name))
            continue
        changed_entries.append(
            (humanize_object_type(object_change.key.object_type), object_change.key.name)
        )

    return tuple(dict.fromkeys(changed_entries))


def render_workflow_summary(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    lines: list[str] = []
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        live_targets: tuple[str, ...] = live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        )
        workflow_target_name: str = live_targets[0] if live_targets else subtree.root_key.name
        lines.append(f"- prepare staged objects for subtree rooted at {workflow_target_name}")
        lines.append(f"- backfill from {subtree.upstream_boundary_key.name}")
        if live_targets:
            lines.append(f"- audit staged {', '.join(live_targets)}")
            lines.append(f"- publish {', '.join(live_targets)}")
        else:
            lines.append(f"- audit subtree rooted at {workflow_target_name}")
            lines.append(f"- publish subtree rooted at {workflow_target_name}")
    return lines


def format_backfill_policy(subtree: RebuildSubtree) -> str:
    if subtree.configured_backfill_mode == SchemaChangeBackfillMode.FULL:
        return str(SchemaChangeBackfillMode.FULL)
    if subtree.execution_lookback_seconds is None:
        return str(SchemaChangeBackfillMode.BOUNDED)
    return f"bounded({format_duration_seconds(subtree.execution_lookback_seconds)})"


def describe_subtree_rebuild_behavior(subtree: RebuildSubtree) -> str:
    if subtree.execution_mode == REBUILD_EXECUTION_MODE_FULL:
        if subtree.forced_full_refresh:
            return "full refresh requested; replay all history for this subtree"
        if subtree.resolved_bounded_replay_fallback == BoundedReplayFallback.FULL_REFRESH:
            return "full refresh will be used instead of bounded replay"
        return "refresh all history for this subtree"
    if subtree.forced_start_time is not None:
        return f"bounded replay with history from {subtree.forced_start_time} onward"
    if subtree.resolved_bounded_replay_fallback == BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY:
        return "bounded replay without history; older rows will not be preserved"
    if subtree.execution_mode == REBUILD_EXECUTION_MODE_SEEDED_BOUNDED:
        if subtree.execution_lookback_seconds is None:
            return (
                "bounded replay with history will keep older active rows and replay the recent tail"
            )
        return (
            "bounded replay with history will keep older active rows and replay the last "
            f"{format_duration_seconds(subtree.execution_lookback_seconds)}"
        )
    if subtree.execution_lookback_seconds is None:
        return "bounded replay without history will replay only the recent tail in the new schema"
    return (
        "bounded replay without history will replay only the last "
        f"{format_duration_seconds(subtree.execution_lookback_seconds)} in the new schema"
    )


def unsupported_replay_detail_lines(subtree: RebuildSubtree) -> tuple[str, ...]:
    if subtree.history_preserving_bounded_supported:
        return ()
    if subtree.resolved_bounded_replay_fallback == BoundedReplayFallback.FULL_REFRESH:
        return (
            "bounded replay cannot preserve prior history for this target",
            "bounded replay fallback: full_refresh",
        )
    if subtree.resolved_bounded_replay_fallback == BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY:
        return (
            "bounded replay cannot preserve prior history for this target",
            "bounded replay fallback: bounded_without_history",
        )
    return ()


def format_duration_seconds(seconds: int) -> str:
    if seconds % (24 * 60 * 60) == 0:
        return f"{seconds // (24 * 60 * 60)}d"
    if seconds % (60 * 60) == 0:
        return f"{seconds // (60 * 60)}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def humanize_object_type(value: str) -> str:
    object_type_by_value: dict[str, str] = {
        DESIRED_OBJECT_TYPE_TABLE: "table",
        DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW: "materialized view",
        DESIRED_OBJECT_TYPE_KAFKA_TABLE: "kafka table",
    }
    return object_type_by_value.get(value, value.replace("_", " "))
