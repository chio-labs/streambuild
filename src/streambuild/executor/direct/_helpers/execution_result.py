"""Decode direct build and audit evidence from authoritative workflow results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from streambuild.adapter.models import (
    AdapterOwnershipRecord,
    AdapterReplayCoverageRange,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.models import CompiledSource
from streambuild.executor.auditing.models import SqlAuditResult, SqlAuditRunResult
from streambuild.executor.direct._helpers.ownership import build_direct_ownership_records
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
    DirectBuildRequest,
    DirectBuildResult,
    DirectReplayBoundary,
    DirectRootReplayResult,
)
from streambuild.executor.workflow.models import WorkflowExecutionResult, WorkflowStatementResult


def build_direct_execution_result(
    *,
    request: DirectBuildRequest,
    execution: WorkflowExecutionResult,
) -> DirectBuildExecutionResult:
    """Decode direct lifecycle evidence without reading target artifacts or warehouse state."""

    results_by_step_id: dict[str, WorkflowStatementResult] = {
        result.step_id: result for result in execution.statement_results
    }
    boundaries: tuple[DirectReplayBoundary, ...] = _boundaries(execution=execution)
    ownership_records: tuple[AdapterOwnershipRecord, ...] = _ownership_records(
        request=request,
        result=results_by_step_id.get("read_final_ownership"),
    )
    return DirectBuildExecutionResult(
        build_result=DirectBuildResult(
            database=request.database,
            ownership_records=ownership_records,
            preserved_source_relation_names=_preserved_source_names(
                request=request,
                results_by_step_id=results_by_step_id,
            ),
            created_source_relation_names=_created_source_names(
                request=request,
                results_by_step_id=results_by_step_id,
            ),
            dropped_relation_names=tuple(
                operation.relation_name for operation in request.plan.teardown_operations
            ),
            created_relation_names=tuple(
                operation.relation_name for operation in request.plan.creation_operations
            ),
            boundary_time=_boundary_time(request=request, boundaries=boundaries),
            boundaries=boundaries,
            replay_results=_replay_results(request=request, execution=execution),
            effective_start_time=request.effective_start_time,
        ),
        audit_result=_audit_result(
            request=request,
            results_by_step_id=results_by_step_id,
        ),
    )


def _boundaries(*, execution: WorkflowExecutionResult) -> tuple[DirectReplayBoundary, ...]:
    boundaries: list[DirectReplayBoundary] = []
    result: WorkflowStatementResult
    for result in execution.statement_results:
        if not result.step_id.startswith("read_boundary_") or result.query_result is None:
            continue
        row: tuple[object, ...]
        for row in result.query_result.rows:
            boundaries.append(
                DirectReplayBoundary(
                    model_name=str(row[0]),
                    driving_input_relation_name=str(row[1]),
                    replay_boundary_mode=str(row[2]),
                    boundary_key=str(row[3]),
                    cutoff_value=str(row[4]),
                    cutoff_inclusive=True,
                )
            )
    return tuple(boundaries)


def _ownership_records(
    *, request: DirectBuildRequest, result: WorkflowStatementResult | None
) -> tuple[AdapterOwnershipRecord, ...]:
    if result is None or result.query_result is None:
        return build_direct_ownership_records(
            plan=request.plan,
            database=request.database,
            tool_version=request.tool_version,
            replay_coverage=(),
        )
    return tuple(_ownership_record(row) for row in result.query_result.rows)


def _ownership_record(row: tuple[object, ...]) -> AdapterOwnershipRecord:
    payloads: list[dict[str, object]] = cast(list[dict[str, object]], json.loads(str(row[7])))
    return AdapterOwnershipRecord(
        database_name=str(row[0]),
        relation_name=str(row[1]),
        resource_kind=str(row[2]),
        logical_model_database=None if row[3] is None else str(row[3]),
        logical_model_name=str(row[4]),
        owning_mode=str(row[5]),
        tool_version=str(row[6]),
        replay_coverage=tuple(
            AdapterReplayCoverageRange(
                driving_input_relation_name=str(payload["driving_input_relation_name"]),
                replay_boundary_mode=str(payload["replay_boundary_mode"]),
                boundary_key=str(payload["boundary_key"]),
                source_partition_column_name=(str(payload["source_partition_column_name"]) or None),
                source_position_column_name=str(payload["source_position_column_name"]),
                source_timestamp_column_name=(str(payload["source_timestamp_column_name"]) or None),
                lower_value=str(payload["lower_value"]),
                upper_value=str(payload["upper_value"]),
            )
            for payload in payloads
        ),
    )


def _replay_results(
    *, request: DirectBuildRequest, execution: WorkflowExecutionResult
) -> tuple[DirectRootReplayResult, ...]:
    model_name_by_segment: dict[str, str] = {
        _step_segment(entry.model_key.name): entry.model_key.name for entry in request.plan.entries
    }
    results: list[DirectRootReplayResult] = []
    result: WorkflowStatementResult
    for result in execution.statement_results:
        if not result.step_id.startswith("replay_") or result.mutation_result is None:
            continue
        segment: str = result.step_id.removeprefix("replay_")
        results.append(
            DirectRootReplayResult(
                model_name=model_name_by_segment[segment],
                written_rows=result.mutation_result.written_rows,
            )
        )
    return tuple(results)


def _audit_result(
    *,
    request: DirectBuildRequest,
    results_by_step_id: dict[str, WorkflowStatementResult],
) -> SqlAuditRunResult:
    audit_results: list[SqlAuditResult] = []
    for audit_index, audit in enumerate(request.audits, start=1):
        prefix: str = f"audit_{audit_index}_{_step_segment(audit.name)}"
        count_result: WorkflowStatementResult = results_by_step_id[f"{prefix}_count"]
        sample_result: WorkflowStatementResult = results_by_step_id[f"{prefix}_sample"]
        error_message: str | None = count_result.error_message or sample_result.error_message
        count: int = 1 if count_result.error_message is not None else _audit_count(count_result)
        sample_column_names: tuple[str, ...] = (
            () if sample_result.query_result is None else sample_result.query_result.column_names
        )
        sample_rows: tuple[tuple[object, ...], ...] = (
            () if sample_result.query_result is None else sample_result.query_result.rows
        )
        audit_results.append(
            SqlAuditResult(
                file_path=Path(audit.name),
                referenced_model_names=(),
                severity=audit.severity,
                passed=error_message is None and count == 0,
                failing_row_count=count,
                sample_column_names=sample_column_names,
                sample_rows=sample_rows,
                description=audit.description,
                name=audit.name,
                error_message=error_message,
            )
        )
    return SqlAuditRunResult(audit_results=tuple(audit_results))


def _audit_count(result: WorkflowStatementResult) -> int:
    if result.query_result is None or not result.query_result.rows:
        return 0
    return int(str(result.query_result.rows[0][0]))


def _created_source_names(
    *, request: DirectBuildRequest, results_by_step_id: dict[str, WorkflowStatementResult]
) -> tuple[str, ...]:
    source_names: tuple[str, ...] = _managed_source_relation_names(request=request)
    return tuple(
        name
        for name in source_names
        if f"prepare_source_{_step_segment(name)}" in results_by_step_id
        or f"activate_source_{_step_segment(name)}" in results_by_step_id
    )


def _preserved_source_names(
    *, request: DirectBuildRequest, results_by_step_id: dict[str, WorkflowStatementResult]
) -> tuple[str, ...]:
    created_names: frozenset[str] = frozenset(
        _created_source_names(request=request, results_by_step_id=results_by_step_id)
    )
    return tuple(
        name
        for name in _managed_source_relation_names(request=request)
        if name not in created_names
    )


def _managed_source_relation_names(*, request: DirectBuildRequest) -> tuple[str, ...]:
    names: list[str] = []
    source: CompiledSource
    for source in request.realized_project.project.sources:
        resource: object
        for resource in request.realized_project.resources_by_logical_key[source.key]:
            if hasattr(resource, "name"):
                names.append(str(resource.name))
    return tuple(names)


def _boundary_time(
    *, request: DirectBuildRequest, boundaries: tuple[DirectReplayBoundary, ...]
) -> str:
    if request.boundary_time is not None:
        return request.boundary_time
    if boundaries:
        scalar_boundary: DirectReplayBoundary = boundaries[-1]
        if scalar_boundary.replay_boundary_mode != AdapterReplayBoundaryMode.OFFSETS:
            return scalar_boundary.cutoff_value
    return "warehouse"


def _step_segment(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)
