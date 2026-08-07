"""Publish direct workflow result decoding."""

from streambuild.executor.direct._helpers.execution_result import (
    build_direct_execution_result as _build_direct_execution_result,
)
from streambuild.executor.direct.models import (
    DirectBuildExecutionResult,
    DirectBuildRequest,
    DirectReplayCapture,
)
from streambuild.executor.workflow.models import WorkflowExecutionResult


def build_direct_execution_result(
    *,
    request: DirectBuildRequest,
    execution: WorkflowExecutionResult,
    captures: tuple[DirectReplayCapture, ...],
) -> DirectBuildExecutionResult:
    """Decode one direct build from its in-memory workflow evidence."""

    return _build_direct_execution_result(
        request=request,
        execution=execution,
        captures=captures,
    )
