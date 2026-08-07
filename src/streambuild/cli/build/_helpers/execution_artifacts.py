"""Render truthful terminal evidence for direct build artifacts."""

from __future__ import annotations

import json

from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.executor.direct.models import DirectBuildRequest, DirectReplayCapture
from streambuild.executor.workflow.models import WorkflowExecutionResult, WorkflowStatementResult


def render_direct_execution_json(
    *,
    request: DirectBuildRequest,
    status: str,
    captures: tuple[DirectReplayCapture, ...],
    execution: WorkflowExecutionResult,
    failed_step_id: str | None,
    error_message: str | None,
    audit_result: SqlAuditRunResult | None = None,
) -> str:
    """Render bounded direct runtime evidence without creating recovery state."""

    payload: dict[str, object] = {
        "status": status,
        "workflow_id": request.workflow_id,
        "database": request.database,
        "captured_roots": [_capture_payload(capture) for capture in captures],
        "completed_steps": [result.step_id for result in execution.statement_results],
        "failed_step": failed_step_id,
        "error_message": error_message,
        "audit_error_failure_count": (
            None if audit_result is None else audit_result.error_failure_count
        ),
        "audit_warning_failure_count": (
            None if audit_result is None else audit_result.warning_failure_count
        ),
        "statement_outcomes": [
            _statement_result_payload(result) for result in execution.statement_results
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _capture_payload(capture: DirectReplayCapture) -> dict[str, object]:
    return {
        "capture_id": capture.capture_id,
        "model": capture.logical_model_name,
        "driving_input": capture.driving_input_relation_name,
        "boundary_mode": str(capture.boundary_mode),
        "captured_at": capture.captured_at,
        "ranges": [
            {
                "partition": replay_range.partition_value,
                "lower": replay_range.lower_value,
                "upper": replay_range.upper_value,
                "cutoff": replay_range.replay_cutoff_value,
                "cutoff_inclusive": replay_range.cutoff_inclusive,
            }
            for replay_range in capture.ranges
        ],
    }


def _statement_result_payload(result: WorkflowStatementResult) -> dict[str, object]:
    return {
        "step_id": result.step_id,
        "error_message": result.error_message,
        "written_rows": (
            None if result.mutation_result is None else result.mutation_result.written_rows
        ),
        "returned_rows": None if result.query_result is None else len(result.query_result.rows),
    }
