"""Execute an assembled non-authoritative observation workflow."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement, WorkflowExecutionResult


def execute_observation_workflow(
    *, statements: tuple[WarehouseStatement, ...], connection: AdapterConnection
) -> WorkflowExecutionResult:
    """Execute already assembled observation statements through the mutation gateway."""

    return execute_warehouse_workflow(statements=statements, connection=connection)
