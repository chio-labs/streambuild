"""Plan rendering shared by plan and backfill preview flows."""

from __future__ import annotations

import json

from streambuild.cli.shared._helpers.plan_rendering import (
    changed_object_entries,
    compact_changed_target_summaries,
    diff_target_names,
    new_target_names,
    object_key_payload,
    render_sql_diff_plan_context,
    render_subtree_diagram,
    render_workflow_summary,
    rollout_object_entries,
)
from streambuild.cli.shared.main._cli_style import cli_style
from streambuild.cli.shared.models import CompactChangedTargetSummary
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    PlannedSqlDiff,
    PlannerWarning,
    RebuildSubtree,
)
from streambuild.compiler.shared.models import DesiredMaterializedView, DesiredTable, ObjectKey


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
                    "root_key": object_key_payload(step.root_key),
                    "target_key": None
                    if step.target_key is None
                    else object_key_payload(step.target_key),
                }
                for step in plan.steps
            ],
            "rebuild_subtrees": [
                {
                    "root_key": object_key_payload(subtree.root_key),
                    "upstream_boundary_key": object_key_payload(subtree.upstream_boundary_key),
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
                    "root_key": object_key_payload(warning.root_key),
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
                render_subtree_diagram(subtree=subtree, desired_object_by_key=desired_object_by_key)
            )
        lines.append("")
    if not verbose:
        rendered_new_target_names: tuple[str, ...] = new_target_names(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        )
        if rendered_new_target_names:
            lines.append(cli_style().section("New targets"))
            new_target_name: str
            for new_target_name in rendered_new_target_names:
                lines.append(f"- {new_target_name}")
            lines.append("")
        changed_target_summaries: tuple[CompactChangedTargetSummary, ...] = (
            compact_changed_target_summaries(
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
        changed_objects: tuple[tuple[str, str], ...] = changed_object_entries(
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
                render_sql_diff_plan_context(
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
        for diff_target_name in diff_target_names(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        ):
            lines.append(f"- {diff_target_name}")
        lines.append("Run `stb plan --verbose` to show full diffs")
        lines.append("")
    if verbose and plan.rebuild_subtrees:
        lines.append(cli_style().section("Staged rollout objects"))
        rollout_objects: tuple[tuple[str, str], ...] = rollout_object_entries(
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
            render_workflow_summary(plan=plan, desired_object_by_key=desired_object_by_key)
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
