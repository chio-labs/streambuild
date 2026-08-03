"""Execute an ordered warehouse workflow through the sole mutation gateway."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterMutationResult, AdapterQueryResult
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.models import (
    WarehouseStatement,
    WorkflowExecutionResult,
    WorkflowStatementResult,
)
from streambuild.executor.workflow.types import StatementIntent


def execute_warehouse_workflow(
    *, statements: tuple[WarehouseStatement, ...], connection: AdapterConnection
) -> WorkflowExecutionResult:
    """Execute exact statement bytes in their authoritative tuple order."""

    results: list[WorkflowStatementResult] = []
    statement: WarehouseStatement
    for statement in statements:
        query_result: AdapterQueryResult | None = None
        mutation_result: AdapterMutationResult | None = None
        try:
            if statement.intent == StatementIntent.MUTATION:
                mutation_result = connection.execute_workflow_sql(statement.sql)
            else:
                query_result = connection.query(statement.sql)
        except AdapterError as error:
            if not statement.continue_on_error:
                raise WorkflowExecutionError(
                    failed_step_id=statement.step_id,
                    partial_result=WorkflowExecutionResult(statement_results=tuple(results)),
                    cause=error,
                ) from error
            results.append(
                WorkflowStatementResult(
                    step_id=statement.step_id,
                    query_result=None,
                    mutation_result=None,
                    error_message=str(error),
                )
            )
            continue
        results.append(
            WorkflowStatementResult(
                step_id=statement.step_id,
                query_result=query_result,
                mutation_result=mutation_result,
                error_message=None,
            )
        )
    return WorkflowExecutionResult(statement_results=tuple(results))
