"""Execute a build only after artifact publication grants capability."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import (
    PublishedBuildWorkflow,
    WorkflowExecutionResult,
)
from streambuild.executor.workflow.types import WorkflowEventEmitter


def execute_build_workflow(
    *,
    published_workflow: PublishedBuildWorkflow,
    connection: AdapterConnection,
    emitter: WorkflowEventEmitter | None = None,
) -> WorkflowExecutionResult:
    """Execute the same workflow object carried by its publication capability."""

    if emitter is not None:
        emitter.workflow_prepared(
            statements=published_workflow.workflow.statements,
            workflow_sha256=published_workflow.workflow_sha256,
        )
    return execute_warehouse_workflow(
        statements=published_workflow.workflow.statements,
        connection=connection,
        emitter=emitter,
    )
