"""Publish direct workflow result decoding."""

from streambuild.executor.direct._helpers.execution_result import (
    build_direct_execution_result as _build_direct_execution_result,
)
from streambuild.executor.direct.models import DirectBuildExecutionResult, DirectBuildRequest
from streambuild.executor.workflow.models import WorkflowExecutionResult


def build_direct_execution_result(
    *,
    request: DirectBuildRequest,
    execution: WorkflowExecutionResult,
    failed_audit_step_id: str | None = None,
) -> DirectBuildExecutionResult:
    """Decode one direct build from its in-memory workflow evidence."""

    return _build_direct_execution_result(
        request=request,
        execution=execution,
        failed_audit_step_id=failed_audit_step_id,
    )
