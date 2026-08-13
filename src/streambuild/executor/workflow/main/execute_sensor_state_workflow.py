"""Execute an assembled sensor state persistence workflow."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement, WorkflowExecutionResult


def execute_sensor_state_workflow(
    *, statements: tuple[WarehouseStatement, ...], connection: AdapterConnection
) -> WorkflowExecutionResult:
    """Execute already assembled sensor state statements through the mutation gateway."""

    return execute_warehouse_workflow(statements=statements, connection=connection)
