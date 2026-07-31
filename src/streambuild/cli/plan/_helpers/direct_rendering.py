"""Render direct-mode plans as operator text and machine-readable JSON."""

from __future__ import annotations

import json

from streambuild.cli.plan.constants import DIRECT_MODE_LABEL
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
    PlannerWarning,
)


def render_direct_plan_json(*, plan: DirectPlan, adapter_name: str) -> str:
    """Render one direct plan as deterministic JSON."""

    payload: dict[str, object] = {
        "mode": DIRECT_MODE_LABEL,
        "adapter": adapter_name,
        "database": plan.database,
        "user_scope": [_key_name(key) for key in plan.user_scope],
        "execution_scope": [_key_name(key) for key in plan.execution_scope],
        "prerequisite_scope": [
            _prerequisite_payload(prerequisite) for prerequisite in plan.prerequisite_scope
        ],
        "entries": [_entry_payload(entry) for entry in plan.entries],
        "replay_roots": [_replay_root_payload(root) for root in plan.replay_roots],
        "teardown": [_operation_payload(operation) for operation in plan.teardown_operations],
        "creation": [_operation_payload(operation) for operation in plan.creation_operations],
        "warnings": [_warning_payload(warning) for warning in plan.warnings],
    }
    return json.dumps(payload, indent=2)


def render_direct_plan_text(*, plan: DirectPlan, adapter_name: str) -> str:
    """Render one direct plan as operator-facing text."""

    return "\n".join(
        (
            *_render_header(plan=plan, adapter_name=adapter_name),
            *_render_execution_scope(plan=plan),
            *_render_prerequisites(plan=plan),
            *_render_replay_roots(plan=plan),
            *_render_destructive_actions(plan=plan),
            *_render_warnings(plan=plan),
        )
    )


def _render_header(*, plan: DirectPlan, adapter_name: str) -> tuple[str, ...]:
    return (
        cli_style().title("Direct Plan"),
        cli_style().label_value(label="Adapter", value=adapter_name),
        cli_style().label_value(label="Mode", value=DIRECT_MODE_LABEL),
        cli_style().label_value(label="Database", value=plan.database),
        cli_style().label_value(label="Models to rebuild", value=str(len(plan.execution_scope))),
        cli_style().label_value(label="Replay roots", value=str(len(plan.replay_roots))),
        "",
    )


def _render_execution_scope(*, plan: DirectPlan) -> tuple[str, ...]:
    return (
        cli_style().section("Execution scope"),
        *(
            f"  {_key_name(entry.model_key)}  [{entry.reason}]  {', '.join(entry.relation_names)}"
            for entry in plan.entries
        ),
        "",
    )


def _render_prerequisites(*, plan: DirectPlan) -> tuple[str, ...]:
    return (
        cli_style().section("Preserved prerequisites"),
        *_or_none(
            lines=tuple(
                f"  {_key_name(prerequisite.key)}  {', '.join(prerequisite.relation_names)}"
                for prerequisite in plan.prerequisite_scope
            )
        ),
        "",
    )


def _render_replay_roots(*, plan: DirectPlan) -> tuple[str, ...]:
    lines: list[str] = []
    root: DirectReplayRoot
    for root in plan.replay_roots:
        lines.extend(_render_replay_root(root=root))
    return (cli_style().section("Replay roots"), *_or_none(lines=tuple(lines)), "")


def _render_replay_root(*, root: DirectReplayRoot) -> tuple[str, ...]:
    propagated_names: str = ", ".join(_key_name(key) for key in root.propagated_model_keys)
    return (
        f"  {_key_name(root.model_key)} replays from "
        f"{root.driving_input_relation_name} [{root.replay_boundary_mode}]",
        f"    propagates to: {propagated_names}",
    )


def _render_destructive_actions(*, plan: DirectPlan) -> tuple[str, ...]:
    return (
        cli_style().section("Destructive actions"),
        *(
            f"  {operation.action}  {operation.relation_name}"
            for operation in (*plan.teardown_operations, *plan.creation_operations)
        ),
        "",
    )


def _render_warnings(*, plan: DirectPlan) -> tuple[str, ...]:
    return (
        cli_style().section("Warnings"),
        *_or_none(lines=tuple(f"  - {warning.message}" for warning in plan.warnings)),
    )


def _or_none(*, lines: tuple[str, ...]) -> tuple[str, ...]:
    return lines or ("  - none",)


def _prerequisite_payload(prerequisite: DirectPrerequisite) -> dict[str, object]:
    return {
        "name": prerequisite.key.name,
        "resource_type": str(prerequisite.key.resource_type),
        "relations": list(prerequisite.relation_names),
        "present": prerequisite.present,
        "framework_managed": prerequisite.framework_managed,
    }


def _entry_payload(entry: DirectPlanEntry) -> dict[str, object]:
    return {
        "model": entry.model_key.name,
        "reason": str(entry.reason),
        "relations": list(entry.relation_names),
        "ownership": [
            {
                "relation": classification.relation_name,
                "ownership": str(classification.ownership),
            }
            for classification in entry.ownership
        ],
        "driving_input": (
            None if entry.driving_input_key is None else entry.driving_input_key.name
        ),
        "replay_root": entry.is_replay_root,
    }


def _replay_root_payload(root: DirectReplayRoot) -> dict[str, object]:
    return {
        "model": root.model_key.name,
        "driving_input": root.driving_input_key.name,
        "driving_input_relation": root.driving_input_relation_name,
        "replay_boundary_mode": str(root.replay_boundary_mode),
        "propagates_to": [key.name for key in root.propagated_model_keys],
    }


def _operation_payload(operation: DirectRelationOperation) -> dict[str, object]:
    return {
        "relation": operation.relation_name,
        "action": str(operation.action),
        "model": operation.model_key.name,
    }


def _warning_payload(warning: PlannerWarning) -> dict[str, object]:
    return {"warning_code": warning.warning_code, "message": warning.message}


def _key_name(key: LogicalResourceKey) -> str:
    return key.name
