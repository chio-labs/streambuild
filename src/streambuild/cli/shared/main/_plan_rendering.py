"""Plan rendering shared by plan and backfill preview flows."""

from __future__ import annotations

import json

from streambuild.cli.shared.main._cli_style import cli_style
from streambuild.cli.shared.models import CompactChangedTargetSummary
from streambuild.compiler.compile.models import DesiredState
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
    PlannerWarning,
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


def render_plan_result(
    *,
    plan: DeploymentPlan,
    desired_state: DesiredState,
    database: str,
    json_output: bool,
    verbose: bool = False,
) -> str:
    if json_output:
        payload: dict[str, object] = {
            "steps": [
                {
                    "step_id": step.step_id,
                    "phase": step.phase,
                    "action": step.action,
                    "root_key": _object_key_payload(step.root_key),
                    "target_key": None
                    if step.target_key is None
                    else _object_key_payload(step.target_key),
                }
                for step in plan.steps
            ],
            "rebuild_subtrees": [
                {
                    "root_key": _object_key_payload(subtree.root_key),
                    "upstream_boundary_key": _object_key_payload(subtree.upstream_boundary_key),
                    "strategy": subtree.strategy,
                    "execution_mode": subtree.execution_mode,
                    "forced_full_refresh": subtree.forced_full_refresh,
                    "forced_start_time": subtree.forced_start_time,
                    "requested_start_time": subtree.requested_start_time,
                    "configured_backfill_mode": subtree.configured_backfill_mode,
                    "execution_lookback_seconds": subtree.execution_lookback_seconds,
                    "history_preserving_bounded_supported": (
                        subtree.history_preserving_bounded_supported
                    ),
                    "resolved_bounded_replay_fallback": (subtree.resolved_bounded_replay_fallback),
                }
                for subtree in plan.rebuild_subtrees
            ],
            "warnings": [
                {
                    "warning_code": warning.warning_code,
                    "root_key": _object_key_payload(warning.root_key),
                    "message": warning.message,
                }
                for warning in plan.warnings
            ],
            "sql_diffs": [
                {
                    "object_type": sql_diff.object_type,
                    "name": sql_diff.name,
                    "diff_lines": list(sql_diff.diff_lines),
                }
                for sql_diff in plan.sql_diffs
            ],
        }
        return json.dumps(payload, indent=2)

    lines: list[str] = [
        cli_style().title("Plan Ready"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(label="Subtrees to rebuild", value=str(len(plan.rebuild_subtrees))),
        cli_style().label_value(label="Planned steps", value=str(len(plan.steps))),
        "",
    ]
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView] = {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, (DesiredTable, DesiredMaterializedView))
    }
    if plan.rebuild_subtrees:
        lines.append(cli_style().section("Subtrees"))
        subtree: RebuildSubtree
        for index, subtree in enumerate(plan.rebuild_subtrees, start=1):
            if index > 1:
                lines.append("")
            lines.append(cli_style().subsection(f"Subtree {index}"))
            lines.extend(
                _render_subtree_diagram(
                    subtree=subtree, desired_object_by_key=desired_object_by_key
                )
            )
        lines.append("")
    if not verbose:
        new_target_names: tuple[str, ...] = _new_target_names(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        )
        if new_target_names:
            lines.append(cli_style().section("New targets"))
            new_target_name: str
            for new_target_name in new_target_names:
                lines.append(f"- {new_target_name}")
            lines.append("")
        changed_target_summaries: tuple[CompactChangedTargetSummary, ...] = (
            _compact_changed_target_summaries(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
        if changed_target_summaries:
            lines.append(cli_style().section("Changes detected"))
            changed_target_summary: CompactChangedTargetSummary
            for index, changed_target_summary in enumerate(changed_target_summaries):
                if index > 0:
                    lines.append("")
                lines.append(changed_target_summary.target_name)
                detail_line: str
                for detail_line in changed_target_summary.detail_lines:
                    lines.append(f"- {detail_line}")
            lines.append("")
    if verbose:
        changed_objects: tuple[tuple[str, str], ...] = _changed_object_entries(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        )
        if changed_objects:
            lines.append(cli_style().section("Changed objects"))
            changed_object: tuple[str, str]
            for changed_object in changed_objects:
                lines.append(f"- {changed_object[0]}: {changed_object[1]}")
            lines.append("")
    if verbose and plan.sql_diffs:
        lines.append(cli_style().section("SQL diffs"))
        sql_diff: PlannedSqlDiff
        for sql_diff in plan.sql_diffs:
            lines.append("")
            lines.append(
                cli_style().subsection(
                    f"{sql_diff.object_type.title()}: {cli_style().object_name(text=sql_diff.name)}"
                )
            )
            lines.extend(
                _render_sql_diff_plan_context(
                    sql_diff=sql_diff,
                    plan=plan,
                    desired_object_by_key=desired_object_by_key,
                )
            )
            lines.extend(cli_style().diff_lines(sql_diff.diff_lines))
        lines.append("")
    if not verbose and plan.sql_diffs:
        lines.append(cli_style().section("Diffs"))
        diff_target_name: str
        for diff_target_name in _diff_target_names(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        ):
            lines.append(f"- {diff_target_name}")
        lines.append("Run `stb plan --verbose` to show full diffs")
        lines.append("")
    if verbose and plan.rebuild_subtrees:
        lines.append(cli_style().section("Staged rollout objects"))
        rollout_objects: tuple[tuple[str, str], ...] = _rollout_object_entries(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        )
        if not rollout_objects:
            lines.append("- none")
        else:
            rollout_object: tuple[str, str]
            for rollout_object in rollout_objects:
                lines.append(f"- {rollout_object[0]}: {rollout_object[1]}")
        lines.append("")
    if verbose and plan.steps:
        lines.append(cli_style().section("Workflow"))
        lines.extend(
            _render_workflow_summary(plan=plan, desired_object_by_key=desired_object_by_key)
        )
        lines.append("")
    lines.append(cli_style().section("Warnings"))
    if not plan.warnings:
        lines.append("- none")
    else:
        warning: PlannerWarning
        for warning in plan.warnings:
            style = cli_style()
            lines.append(
                f"- {style.warning(warning.root_key.name)}: {style.warning(warning.message)}"
            )
    return "\n".join(lines)


def _object_key_payload(key: ObjectKey) -> dict[str, str | None]:
    return {
        "database": key.database,
        "object_type": key.object_type,
        "name": key.name,
    }


def _render_subtree_diagram(
    *,
    subtree: RebuildSubtree,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    live_targets: tuple[str, ...] = _live_target_names(
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


def _live_target_names(
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


def _render_sql_diff_plan_context(
    *,
    sql_diff: PlannedSqlDiff,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    subtree: RebuildSubtree | None = _subtree_for_key(
        rebuild_subtrees=plan.rebuild_subtrees, key=sql_diff.key
    )
    if subtree is None:
        return []
    lines: list[str] = []
    live_targets: tuple[str, ...] = _live_target_names(
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

    schema_change: PlannedObjectChange | None = _schema_change_for_subtree(
        subtree=subtree,
        object_changes=plan.object_changes,
    )
    if sql_diff.object_type == DESIRED_OBJECT_TYPE_TABLE and schema_change is not None:
        if subtree.configured_backfill_mode is not None:
            lines.append(
                cli_style().label_value(
                    label="Schema-change backfill", value=_format_backfill_policy(subtree)
                )
            )
        lines.append(
            cli_style().label_value(label="Plan", value=_describe_subtree_rebuild_behavior(subtree))
        )
    return lines


def _subtree_for_key(
    *, rebuild_subtrees: tuple[RebuildSubtree, ...], key: ObjectKey
) -> RebuildSubtree | None:
    subtree: RebuildSubtree
    for subtree in rebuild_subtrees:
        if key == subtree.root_key or key in subtree.affected_keys:
            return subtree
    return None


def _schema_change_for_subtree(
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


def _diff_target_names(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    target_names: list[str] = []
    sql_diff: PlannedSqlDiff
    for sql_diff in plan.sql_diffs:
        subtree: RebuildSubtree | None = _subtree_for_key(
            rebuild_subtrees=plan.rebuild_subtrees, key=sql_diff.key
        )
        if subtree is None:
            target_names.append(sql_diff.name)
            continue
        live_targets: tuple[str, ...] = _live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        )
        target_names.extend(live_targets or (sql_diff.name,))
    return tuple(dict.fromkeys(target_names))


def _new_target_names_for_subtree(
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


def _new_target_names(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[str, ...]:
    new_target_names: list[str] = []
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        subtree_new_target_names: tuple[str, ...] = _new_target_names_for_subtree(
            subtree=subtree,
            object_changes=plan.object_changes,
        )
        if subtree_new_target_names:
            new_target_names.extend(subtree_new_target_names)
            continue
        live_target_name: str
        for live_target_name in _live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            if _target_is_new(
                target_name=live_target_name,
                subtree=subtree,
                object_changes=plan.object_changes,
            ):
                new_target_names.append(live_target_name)
    return tuple(dict.fromkeys(new_target_names))


def _target_is_new(
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


def _compact_changed_target_summaries(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> tuple[CompactChangedTargetSummary, ...]:
    detail_lines_by_target_name: dict[str, list[str]] = {}
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        live_target_name: str
        for live_target_name in _live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            if _target_is_new(
                target_name=live_target_name,
                subtree=subtree,
                object_changes=plan.object_changes,
            ):
                continue
            detail_lines: tuple[str, ...] = _compact_changed_target_detail_lines(
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


def _compact_changed_target_detail_lines(
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
                detail_lines.append(f"plan: {_describe_subtree_rebuild_behavior(subtree)}")
                continue
            requested_start_time: str | None = (
                subtree.requested_start_time or object_change.forced_start_time
            )
            if requested_start_time is not None:
                detail_lines.append(f"start time requested: {requested_start_time}")
                detail_lines.extend(_unsupported_replay_detail_lines(subtree))
                detail_lines.append(f"plan: {_describe_subtree_rebuild_behavior(subtree)}")
                continue
            if object_change.schema_change_kind is not None:
                detail_lines.append("table schema changed")
                if subtree.configured_backfill_mode is not None:
                    detail_lines.append(
                        f"schema-change backfill: {_format_backfill_policy(subtree)}"
                    )
                detail_lines.extend(_unsupported_replay_detail_lines(subtree))
                detail_lines.append(f"plan: {_describe_subtree_rebuild_behavior(subtree)}")
                continue
            if object_change.change_type in {
                PLANNED_CHANGE_TYPE_REPLACE,
                PLANNED_CHANGE_TYPE_REBUILD,
            }:
                detail_lines.append("table definition changed")
    return tuple(dict.fromkeys(detail_lines))


def _rollout_object_entries(
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
        for live_target_name in _live_target_names(
            subtree=subtree,
            desired_object_by_key=desired_object_by_key,
        ):
            rollout_objects.append(("live target", live_target_name))

    return tuple(dict.fromkeys(rollout_objects))


def _changed_object_entries(
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
            (_humanize_object_type(object_change.key.object_type), object_change.key.name)
        )

    return tuple(dict.fromkeys(changed_entries))


def _render_workflow_summary(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView],
) -> list[str]:
    lines: list[str] = []
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        live_targets: tuple[str, ...] = _live_target_names(
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


def _format_backfill_policy(subtree: RebuildSubtree) -> str:
    if subtree.configured_backfill_mode == SchemaChangeBackfillMode.FULL:
        return str(SchemaChangeBackfillMode.FULL)
    if subtree.execution_lookback_seconds is None:
        return str(SchemaChangeBackfillMode.BOUNDED)
    return f"bounded({_format_duration_seconds(subtree.execution_lookback_seconds)})"


def _describe_subtree_rebuild_behavior(subtree: RebuildSubtree) -> str:
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
            f"{_format_duration_seconds(subtree.execution_lookback_seconds)}"
        )
    if subtree.execution_lookback_seconds is None:
        return "bounded replay without history will replay only the recent tail in the new schema"
    return (
        "bounded replay without history will replay only the last "
        f"{_format_duration_seconds(subtree.execution_lookback_seconds)} in the new schema"
    )


def _unsupported_replay_detail_lines(subtree: RebuildSubtree) -> tuple[str, ...]:
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


def _format_duration_seconds(seconds: int) -> str:
    if seconds % (24 * 60 * 60) == 0:
        return f"{seconds // (24 * 60 * 60)}d"
    if seconds % (60 * 60) == 0:
        return f"{seconds // (60 * 60)}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _humanize_object_type(value: str) -> str:
    object_type_by_value: dict[str, str] = {
        DESIRED_OBJECT_TYPE_TABLE: "table",
        DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW: "materialized view",
        DESIRED_OBJECT_TYPE_KAFKA_TABLE: "kafka table",
    }
    return object_type_by_value.get(value, value.replace("_", " "))
