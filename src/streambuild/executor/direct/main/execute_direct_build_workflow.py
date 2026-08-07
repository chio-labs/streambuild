"""Execute a direct workflow from process-owned replay captures."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.direct._helpers.runtime import (
    execute_direct_build_workflow as _execute_direct_build_workflow,
)
from streambuild.executor.direct.models import DirectBuildWorkflow, DirectRuntimeExecution
from streambuild.executor.workflow.types import WorkflowEventEmitter


def execute_direct_build_workflow(
    *,
    workflow: DirectBuildWorkflow,
    connection: AdapterConnection,
    emitter: WorkflowEventEmitter | None = None,
) -> DirectRuntimeExecution:
    """Execute static direct phases and realize replay SQL from live captures."""

    return _execute_direct_build_workflow(
        workflow=workflow,
        connection=connection,
        emitter=emitter,
    )
