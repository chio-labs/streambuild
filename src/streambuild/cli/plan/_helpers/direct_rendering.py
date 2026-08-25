"""Render direct-mode plans as operator text and machine-readable JSON."""

from __future__ import annotations

import json

from streambuild.cli.plan.constants import DIRECT_MODE_LABEL
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.compiler.compile.models import LogicalResourceKey, ObjectKey
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
    DirectSqlChange,
    PlannerWarning,
)
from streambuild.compiler.planner.types import DirectSqlBaselineStatus

_DEFAULT_DIFF_LINE_LIMIT: int = 12


def render_direct_plan_json(*, plan: DirectPlan, adapter_name: str) -> str:
    """Render one direct plan as deterministic JSON."""

    payload: dict[str, object] = {
        "mode": DIRECT_MODE_LABEL,
        "adapter": adapter_name,
        "database": plan.database,
        "start_time": plan.effective_start_time,
        "selection_mode": str(plan.selection_mode),
        "user_scope": [_logical_key_payload(key) for key in plan.user_scope],
        "execution_scope": [_logical_key_payload(key) for key in plan.execution_scope],
        "prerequisite_execution_scope": [
            _logical_key_payload(key) for key in plan.prerequisite_execution_scope
        ],
        "prerequisite_scope": [
            _prerequisite_payload(prerequisite) for prerequisite in plan.prerequisite_scope
        ],
        "entries": [_entry_payload(entry) for entry in plan.entries],
        "replay_roots": [_replay_root_payload(root) for root in plan.replay_roots],
        "teardown": [_operation_payload(operation) for operation in plan.teardown_operations],
        "creation": [_operation_payload(operation) for operation in plan.creation_operations],
        "warnings": [_warning_payload(warning) for warning in plan.warnings],
    }
    return json.dumps(payload, indent=2) + "\n"


def render_direct_plan_text(*, plan: DirectPlan, adapter_name: str, verbose: bool = False) -> str:
    """Render one direct plan as operator-facing text."""

    lines: list[str] = [cli_style().title(f"Direct plan  {plan.database}"), ""]
    if verbose:
        lines.append(cli_style().label_value(label="Adapter", value=adapter_name))
        lines.append("")
    lines.extend(_render_rebuild_paths(plan=plan))
    lines.extend((cli_style().section("Model decisions"), ""))
    entry: DirectPlanEntry
    for entry in plan.entries:
        lines.extend(_render_model_decision(entry=entry, verbose=verbose))
    if plan.effective_start_time is not None:
        lines.append(cli_style().label_value(label="Start time", value=plan.effective_start_time))
    warning: PlannerWarning
    for warning in plan.warnings:
        lines.append(cli_style().warning(f"warning  {warning.message}"))
    lines.append(_summary_line(plan=plan))
    return "\n".join(lines)


def _render_rebuild_paths(*, plan: DirectPlan) -> tuple[str, ...]:
    lines: list[str] = [cli_style().section("Rebuild paths"), ""]
    covered_model_keys: set[LogicalResourceKey] = set()
    roots_by_source: dict[tuple[str, str], list[DirectReplayRoot]] = {}
    replay_root: DirectReplayRoot
    for replay_root in plan.replay_roots:
        source_identity: tuple[str, str] = (
            replay_root.driving_input_relation_name,
            str(replay_root.replay_boundary_mode),
        )
        roots_by_source.setdefault(source_identity, []).append(replay_root)
    source_identity: tuple[str, str]
    replay_roots: list[DirectReplayRoot]
    for source_index, (source_identity, replay_roots) in enumerate(roots_by_source.items()):
        if source_index:
            lines.append("")
        lines.append(f"[replay source] {source_identity[0]} [{source_identity[1]}]")
        for root_index, replay_root in enumerate(replay_roots):
            root_is_last: bool = root_index == len(replay_roots) - 1
            root_branch: str = "└──" if root_is_last else "├──"
            lines.append(f"{root_branch} [replay root] {_key_name(replay_root.model_key)}")
            propagated_keys: tuple[LogicalResourceKey, ...] = tuple(
                key for key in replay_root.propagated_model_keys if key != replay_root.model_key
            )
            child_prefix: str = "    " if root_is_last else "│   "
            for child_index, model_key in enumerate(propagated_keys):
                child_branch: str = "└──" if child_index == len(propagated_keys) - 1 else "├──"
                lines.append(f"{child_prefix}{child_branch} [rebuild] {_key_name(model_key)}")
            covered_model_keys.update(replay_root.propagated_model_keys)
    entry: DirectPlanEntry
    for entry in plan.entries:
        if entry.model_key not in covered_model_keys:
            lines.append(f"[rebuild] {_key_name(entry.model_key)}")
    lines.append("")
    return tuple(lines)


def _render_model_decision(*, entry: DirectPlanEntry, verbose: bool) -> tuple[str, ...]:
    lines: list[str] = [cli_style().object_name(text=_key_name(entry.model_key))]
    if entry.sql_change is not None:
        lines.extend(_render_sql_change(sql_change=entry.sql_change, verbose=verbose))
    lines.append(f"  {cli_style().label('reason')}  {entry.reason}")
    lines.append(f"  {cli_style().label('rebuild')}  {', '.join(entry.relation_names)}")
    lines.append("")
    return tuple(lines)


def _render_sql_change(*, sql_change: DirectSqlChange, verbose: bool) -> tuple[str, ...]:
    status: DirectSqlBaselineStatus = DirectSqlBaselineStatus(sql_change.status)
    label: str = {
        DirectSqlBaselineStatus.FIRST_BASELINE: "first SQL baseline",
        DirectSqlBaselineStatus.QUERY_CHANGED: "SQL changed",
        DirectSqlBaselineStatus.NO_QUERY_CHANGE: "no SQL change",
        DirectSqlBaselineStatus.BASELINE_UNAVAILABLE: "SQL baseline unavailable",
    }[status]
    lines: list[str] = [f"  {label}"]
    if sql_change.warning is not None:
        lines.append(f"    {cli_style().warning(sql_change.warning)}")
    if sql_change.unified_diff is not None:
        diff_lines: tuple[str, ...] = tuple(sql_change.unified_diff.splitlines())
        visible_lines: tuple[str, ...] = (
            diff_lines if verbose else diff_lines[:_DEFAULT_DIFF_LINE_LIMIT]
        )
        lines.extend(f"    {line}" for line in cli_style().diff_lines(visible_lines))
        if not verbose and len(diff_lines) > len(visible_lines):
            lines.append(cli_style().muted("    ... use --verbose for the complete diff"))
    return tuple(lines)


def _summary_line(*, plan: DirectPlan) -> str:
    model_count: int = len(plan.execution_scope)
    relation_count: int = len(plan.creation_operations)
    replay_count: int = len(plan.replay_roots)
    return (
        f"{model_count} model{'s' if model_count != 1 else ''} selected, "
        f"{relation_count} relation{'s' if relation_count != 1 else ''} rebuilt, "
        f"{replay_count} replay root{'s' if replay_count != 1 else ''}"
    )


def _prerequisite_payload(prerequisite: DirectPrerequisite) -> dict[str, object]:
    return {
        "key": _logical_key_payload(prerequisite.key),
        "relation_names": list(prerequisite.relation_names),
        "present": prerequisite.present,
        "framework_managed": prerequisite.framework_managed,
    }


def _entry_payload(entry: DirectPlanEntry) -> dict[str, object]:
    return {
        "model_key": _logical_key_payload(entry.model_key),
        "reason": str(entry.reason),
        "relation_names": list(entry.relation_names),
        "resource_kinds": [str(kind) for kind in entry.resource_kinds],
        "driving_input_key": (
            None
            if entry.driving_input_key is None
            else _logical_key_payload(entry.driving_input_key)
        ),
        "is_replay_root": entry.is_replay_root,
        "sql_change": (None if entry.sql_change is None else _sql_change_payload(entry.sql_change)),
    }


def _sql_change_payload(sql_change: DirectSqlChange) -> dict[str, object]:
    return {
        "status": str(sql_change.status),
        "current_sql": sql_change.current_sql,
        "current_hash": sql_change.current_hash,
        "previous_sql": sql_change.previous_sql,
        "previous_hash": sql_change.previous_hash,
        "unified_diff": sql_change.unified_diff,
        "warning": sql_change.warning,
    }


def _replay_root_payload(root: DirectReplayRoot) -> dict[str, object]:
    return {
        "model_key": _logical_key_payload(root.model_key),
        "driving_input_key": _logical_key_payload(root.driving_input_key),
        "driving_input_relation_name": root.driving_input_relation_name,
        "driving_input_replay_columns": {
            "partition": root.driving_input_replay_columns.partition,
            "offset": root.driving_input_replay_columns.offset,
            "timestamp": root.driving_input_replay_columns.timestamp,
            "landed_at": root.driving_input_replay_columns.landed_at,
            "cursor": root.driving_input_replay_columns.cursor,
        },
        "replay_boundary_mode": str(root.replay_boundary_mode),
        "propagated_model_keys": [_logical_key_payload(key) for key in root.propagated_model_keys],
        "has_aggregate_semantics": root.has_aggregate_semantics,
        "settings": dict(root.replay_settings),
    }


def _operation_payload(operation: DirectRelationOperation) -> dict[str, object]:
    return {
        "relation_name": operation.relation_name,
        "action": str(operation.action),
        "model_key": _logical_key_payload(operation.model_key),
        "resource_kind": str(operation.resource_kind),
    }


def _warning_payload(warning: PlannerWarning) -> dict[str, object]:
    return {
        "warning_code": warning.warning_code,
        "message": warning.message,
        "root_key": _object_key_payload(warning.root_key),
        "target_key": (
            None if warning.target_key is None else _object_key_payload(warning.target_key)
        ),
    }


def _key_name(key: LogicalResourceKey) -> str:
    return key.name


def _logical_key_payload(key: LogicalResourceKey) -> dict[str, str]:
    return {"resource_type": str(key.resource_type), "name": key.name}


def _object_key_payload(key: ObjectKey) -> dict[str, str | None]:
    return {"database": key.database, "object_type": key.object_type, "name": key.name}
