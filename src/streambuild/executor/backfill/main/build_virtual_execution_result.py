"""Publish virtual workflow result assembly outside executor internals."""

from streambuild.executor.backfill._helpers.execution_result import (
    build_virtual_execution_result as _build_virtual_execution_result,
)
from streambuild.executor.backfill.models import (
    BackfillBootstrapRequest,
    BackfillExecutionResult,
    RootBackfillReport,
)
from streambuild.executor.workflow.models import WorkflowExecutionResult


def build_virtual_execution_result(
    *,
    request: BackfillBootstrapRequest,
    root_reports: tuple[RootBackfillReport, ...],
    existing_relation_names: frozenset[str],
    execution: WorkflowExecutionResult,
) -> BackfillExecutionResult:
    """Return virtual output decoded from exact workflow execution evidence."""

    return _build_virtual_execution_result(
        request=request,
        root_reports=root_reports,
        existing_relation_names=existing_relation_names,
        execution=execution,
    )
