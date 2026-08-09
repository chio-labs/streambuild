"""Selector expansion, replay row counts, and DirectPlan serialization for /api/plan."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterReplayColumns
from streambuild.compiler.compile.models import CompiledPipeline, LogicalResourceKey
from streambuild.compiler.discovery.models import PipelineProtection
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
    DirectSqlChange,
)

_TIMESTAMP_DRIVEN_MODES: frozenset[ReplayLineageMode] = frozenset(
    {ReplayLineageMode.TIMESTAMP, ReplayLineageMode.CURSOR}
)


def build_plan_payload(
    *,
    plan: DirectPlan,
    analysis: CompileAnalysis,
    selectors: tuple[str, ...],
    start_time: str | None,
    planned_at: str,
    replay_row_counts: dict[str, int | None],
    command: str,
) -> dict[str, object]:
    """Serialize one DirectPlan into the UI plan shape."""

    pipeline_by_model: dict[str, str] = {
        model.key.name: model.pipeline_name for model in analysis.compiled_project.models
    }
    return {
        "database": plan.database,
        "userScope": list(selectors),
        "entries": [
            _entry_payload(entry=entry, pipeline_by_model=pipeline_by_model)
            for entry in plan.entries
        ],
        "prerequisites": [_prerequisite_payload(item) for item in plan.prerequisite_scope],
        "teardown": [_operation_payload(item) for item in plan.teardown_operations],
        "creation": [_operation_payload(item) for item in plan.creation_operations],
        "replayRoots": [
            _replay_root_payload(
                item=item, rows_to_replay=replay_row_counts.get(item.model_key.name)
            )
            for item in plan.replay_roots
        ],
        "warnings": [
            {"code": item.warning_code, "message": item.message} for item in plan.warnings
        ],
        "protections": _protection_payloads(plan=plan, analysis=analysis),
        "replayWindow": (
            {"mode": "full"} if start_time is None else {"mode": "from", "startTime": start_time}
        ),
        "plannedAt": planned_at,
        "command": command,
    }


def _protection_payloads(*, plan: DirectPlan, analysis: CompileAnalysis) -> list[dict[str, str]]:
    execution_keys: frozenset[LogicalResourceKey] = frozenset(plan.execution_scope)
    payloads: list[dict[str, str]] = []
    pipeline: CompiledPipeline
    for pipeline in analysis.compiled_project.pipelines:
        protection: PipelineProtection | None = pipeline.pipeline.protection
        if protection is None or not any(model.key in execution_keys for model in pipeline.models):
            continue
        payloads.append(
            {
                "pipelineName": pipeline.pipeline.name,
                "warning": protection.warning,
                "confirmation": protection.confirmation,
            }
        )
    return payloads


def _entry_payload(
    *,
    entry: DirectPlanEntry,
    pipeline_by_model: dict[str, str],
) -> dict[str, object]:
    return {
        "modelName": entry.model_key.name,
        "pipeline": pipeline_by_model.get(entry.model_key.name),
        "reason": str(entry.reason),
        "relationNames": list(entry.relation_names),
        "resourceKinds": [str(kind) for kind in entry.resource_kinds],
        "drivingInput": None if entry.driving_input_key is None else entry.driving_input_key.name,
        "isReplayRoot": entry.is_replay_root,
        "sqlChange": _sql_change_payload(entry.sql_change),
    }


def _sql_change_payload(sql_change: DirectSqlChange | None) -> dict[str, object] | None:
    if sql_change is None:
        return None
    return {
        "status": str(sql_change.status),
        "unifiedDiff": sql_change.unified_diff,
        "warning": sql_change.warning,
    }


def _prerequisite_payload(item: DirectPrerequisite) -> dict[str, object]:
    return {
        "name": item.key.name,
        "type": str(item.key.resource_type),
        "relationNames": list(item.relation_names),
        "present": item.present,
        "frameworkManaged": item.framework_managed,
    }


def _operation_payload(item: DirectRelationOperation) -> dict[str, object]:
    return {
        "relationName": item.relation_name,
        "action": str(item.action),
        "modelName": item.model_key.name,
        "resourceKind": str(item.resource_kind),
    }


def _replay_root_payload(
    *, item: DirectReplayRoot, rows_to_replay: int | None
) -> dict[str, object]:
    return {
        "modelName": item.model_key.name,
        "drivingInputName": item.driving_input_key.name,
        "drivingInputRelationName": item.driving_input_relation_name,
        "boundaryMode": str(item.replay_boundary_mode),
        "replayColumns": {
            "partition": item.driving_input_replay_columns.partition,
            "offset": item.driving_input_replay_columns.offset,
            "timestamp": item.driving_input_replay_columns.timestamp,
            "landed_at": item.driving_input_replay_columns.landed_at,
            "cursor": item.driving_input_replay_columns.cursor,
        },
        "propagatedModelNames": [key.name for key in item.propagated_model_keys],
        "hasAggregateSemantics": item.has_aggregate_semantics,
        "rowsToReplay": rows_to_replay,
    }


def replay_time_column(*, boundary_mode: str, columns: AdapterReplayColumns) -> str:
    """The column the executor compares a forced start time against for this mode."""

    mode: ReplayLineageMode = ReplayLineageMode(boundary_mode)
    if mode in _TIMESTAMP_DRIVEN_MODES:
        return columns.timestamp
    if mode is ReplayLineageMode.OFFSETS:
        return columns.landed_at or columns.timestamp
    return columns.landed_at


def build_replay_count_query(
    *,
    database: str,
    relation_name: str,
    time_column: str,
    start_time: str | None,
) -> str:
    """Count the rows a replay of this root would read; unbounded for full replay."""

    base: str = f"SELECT count() AS rows FROM `{database}`.`{relation_name}`"
    if start_time is None:
        return base
    literal: str = _escape_time_literal(start_time)
    return f"{base} WHERE `{time_column}` >= toDateTime64('{literal}', 3, 'UTC')"


def count_replay_rows(
    *,
    connection: AdapterConnection,
    database: str,
    plan: DirectPlan,
    start_time: str | None,
) -> dict[str, int | None]:
    """Exact rows-to-replay per replay-root model; None when the anchor is unreadable."""

    counts: dict[str, int | None] = {}
    root: DirectReplayRoot
    for root in plan.replay_roots:
        counts[root.model_key.name] = _count_one_root(
            connection=connection,
            database=database,
            root=root,
            start_time=start_time,
        )
    return counts


def _count_one_root(
    *,
    connection: AdapterConnection,
    database: str,
    root: DirectReplayRoot,
    start_time: str | None,
) -> int | None:
    """One anchor count; a fresh project without the anchor table yields None, not an error."""

    query: str = build_replay_count_query(
        database=database,
        relation_name=root.driving_input_relation_name,
        time_column=replay_time_column(
            boundary_mode=str(root.replay_boundary_mode),
            columns=root.driving_input_replay_columns,
        ),
        start_time=start_time,
    )
    try:
        rows: tuple = connection.query(query).rows
    except AdapterError:
        return None
    if not rows:
        return None
    return int(str(rows[0][0]))


def _escape_time_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
