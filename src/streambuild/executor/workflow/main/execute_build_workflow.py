"""Execute a build only after artifact publication grants capability."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import PublishedBuildWorkflow, WorkflowExecutionResult


def execute_build_workflow(
    *, published_workflow: PublishedBuildWorkflow, connection: AdapterConnection
) -> WorkflowExecutionResult:
    """Execute the same workflow object carried by its publication capability."""

    return execute_warehouse_workflow(
        statements=published_workflow.workflow.statements,
        connection=connection,
    )
