"""Serialize deployment plans and assemble their CLI text sections."""

from __future__ import annotations

import json

from streambuild.cli.plan._helpers.plan_rendering import (
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
from streambuild.cli.plan.constants import VIRTUAL_ENVIRONMENTS_MODE_LABEL
from streambuild.cli.plan.models import CompactChangedTargetSummary
from streambuild.cli.presentation.classes.cli_style import CliStyle
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    ObjectKey,
)
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    PlannedSqlDiff,
    PlannerWarning,
    RebuildSubtree,
)


def render_plan_json(*, plan: DeploymentPlan, adapter_name: str) -> str:
    payload: dict[str, object] = {
        "mode": VIRTUAL_ENVIRONMENTS_MODE_LABEL,
        "adapter": adapter_name,
        "deployment_id": plan.deployment_id,
        "object_changes": [
            {
                "key": object_key_payload(change.key),
                "change_type": change.change_type,
                "force_full_refresh": change.force_full_refresh,
                "forced_start_time": change.forced_start_time,
                "schema_change_kind": change.schema_change_kind,
                "seed_compatibility": change.seed_compatibility,
            }
            for change in plan.object_changes
        ],
        "steps": [
            {
                "step_id": step.step_id,
                "phase": step.phase,
                "action": step.action,
                "root_key": object_key_payload(step.root_key),
                "target_key": None
                if step.target_key is None
                else object_key_payload(step.target_key),
                "physical_name": step.physical_name,
            }
            for step in plan.steps
        ],
        "rebuild_subtrees": [
            _rebuild_subtree_payload(subtree=subtree) for subtree in plan.rebuild_subtrees
        ],
        "prepared_shadow_objects": [
            {
                "logical_key": object_key_payload(prepared.logical_key),
                "physical_name": prepared.physical_name,
                "logical_model_name": prepared.logical_model_name,
            }
            for prepared in plan.prepared_shadow_objects
        ],
        "warnings": [
            {
                "warning_code": warning.warning_code,
                "root_key": object_key_payload(warning.root_key),
                "target_key": None
                if warning.target_key is None
                else object_key_payload(warning.target_key),
                "message": warning.message,
            }
            for warning in plan.warnings
        ],
        "sql_diffs": [
            {
                "key": object_key_payload(sql_diff.key),
                "object_type": sql_diff.object_type,
                "name": sql_diff.name,
                "diff_lines": list(sql_diff.diff_lines),
            }
            for sql_diff in plan.sql_diffs
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _rebuild_subtree_payload(*, subtree: RebuildSubtree) -> dict[str, object]:
    return {
        "root_key": object_key_payload(subtree.root_key),
        "upstream_boundary_key": object_key_payload(subtree.upstream_boundary_key),
        "affected_keys": [object_key_payload(key) for key in subtree.affected_keys],
        "strategy": subtree.strategy,
        "replay_required": subtree.replay_required,
        "execution_mode": subtree.execution_mode,
        "forced_full_refresh": subtree.forced_full_refresh,
        "forced_start_time": subtree.forced_start_time,
        "requested_start_time": subtree.requested_start_time,
        "configured_backfill_mode": subtree.configured_backfill_mode,
        "execution_lookback_seconds": subtree.execution_lookback_seconds,
        "history_preserving_bounded_supported": subtree.history_preserving_bounded_supported,
        "resolved_bounded_replay_fallback": subtree.resolved_bounded_replay_fallback,
    }


def render_plan_text(
    *,
    plan: DeploymentPlan,
    desired_state: DesiredState,
    database: str,
    verbose: bool,
) -> str:
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView] = (
        _desired_object_by_key(desired_state)
    )
    lines: list[str] = _render_header(plan=plan, database=database)
    lines.extend(_render_subtrees(plan=plan, desired_object_by_key=desired_object_by_key))
    if not verbose:
        lines.extend(
            _render_compact_summary(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
    if verbose:
        lines.extend(
            _render_changed_objects(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
        lines.extend(
            _render_sql_diffs(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
    else:
        lines.extend(
            _render_compact_diffs(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
    if verbose and plan.rebuild_subtrees:
        lines.extend(
            _render_rollout_objects(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
    if verbose and plan.steps:
        lines.extend(
            _render_workflow(
                plan=plan,
                desired_object_by_key=desired_object_by_key,
            )
        )
    lines.extend(_render_warnings(plan.warnings))
    return "\n".join(lines)


def _desired_object_by_key(
    desired_state: DesiredState,
) -> dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView]:
    return {
        object_.key: object_
        for object_ in desired_state.objects
        if isinstance(object_, (DesiredTable, DesiredMaterializedView, DesiredView))
    }


def _render_header(*, plan: DeploymentPlan, database: str) -> list[str]:
    return [
        cli_style().title("Plan Ready"),
        cli_style().label_value(label="Database", value=database),
        cli_style().label_value(
            label="Subtrees to rebuild",
            value=str(len(plan.rebuild_subtrees)),
        ),
        cli_style().label_value(label="Planned steps", value=str(len(plan.steps))),
        "",
    ]


def _render_subtrees(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    if not plan.rebuild_subtrees:
        return []
    lines: list[str] = [cli_style().section("Subtrees")]
    subtree: RebuildSubtree
    for index, subtree in enumerate(plan.rebuild_subtrees, start=1):
        if index > 1:
            lines.append("")
        lines.append(cli_style().subsection(f"Subtree {index}"))
        lines.extend(
            render_subtree_diagram(
                subtree=subtree,
                desired_object_by_key=desired_object_by_key,
            )
        )
    lines.append("")
    return lines


def _render_compact_summary(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    lines: list[str] = []
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
    return lines


def _render_changed_objects(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    changed_objects: tuple[tuple[str, str], ...] = changed_object_entries(
        plan=plan,
        desired_object_by_key=desired_object_by_key,
    )
    if not changed_objects:
        return []
    lines: list[str] = [cli_style().section("Changed objects")]
    changed_object: tuple[str, str]
    for changed_object in changed_objects:
        lines.append(f"- {changed_object[0]}: {changed_object[1]}")
    lines.append("")
    return lines


def _render_sql_diffs(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    if not plan.sql_diffs:
        return []
    lines: list[str] = [cli_style().section("SQL diffs")]
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
    return lines


def _render_compact_diffs(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    if not plan.sql_diffs:
        return []
    lines: list[str] = [cli_style().section("Diffs")]
    diff_target_name: str
    for diff_target_name in diff_target_names(
        plan=plan,
        desired_object_by_key=desired_object_by_key,
    ):
        lines.append(f"- {diff_target_name}")
    lines.append("Run `stb plan --verbose` to show full diffs")
    lines.append("")
    return lines


def _render_rollout_objects(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    lines: list[str] = [cli_style().section("Staged rollout objects")]
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
    return lines


def _render_workflow(
    *,
    plan: DeploymentPlan,
    desired_object_by_key: dict[ObjectKey, DesiredTable | DesiredMaterializedView | DesiredView],
) -> list[str]:
    lines: list[str] = [cli_style().section("Workflow")]
    lines.extend(
        render_workflow_summary(
            plan=plan,
            desired_object_by_key=desired_object_by_key,
        )
    )
    lines.append("")
    return lines


def _render_warnings(warnings: tuple[PlannerWarning, ...]) -> list[str]:
    lines: list[str] = [cli_style().section("Warnings")]
    if not warnings:
        lines.append("- none")
        return lines
    warning: PlannerWarning
    for warning in warnings:
        style: CliStyle = cli_style()
        lines.append(f"- {style.warning(warning.root_key.name)}: {style.warning(warning.message)}")
    return lines
