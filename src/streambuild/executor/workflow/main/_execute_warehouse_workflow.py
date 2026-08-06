"""Execute an ordered warehouse workflow through the sole mutation gateway."""

import time

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterMutationResult, AdapterQueryResult
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.models import (
    WarehouseStatement,
    WorkflowExecutionResult,
    WorkflowStatementResult,
)
from streambuild.executor.workflow.types import StatementIntent, WorkflowEventEmitter


def execute_warehouse_workflow(
    *,
    statements: tuple[WarehouseStatement, ...],
    connection: AdapterConnection,
    emitter: WorkflowEventEmitter | None = None,
) -> WorkflowExecutionResult:
    """Execute exact statement bytes in their authoritative tuple order."""

    results: list[WorkflowStatementResult] = []
    statement: WarehouseStatement
    for statement in statements:
        query_result: AdapterQueryResult | None = None
        mutation_result: AdapterMutationResult | None = None
        if emitter is not None:
            emitter.statement_started(statement)
        started_ns: int = time.monotonic_ns()
        try:
            if statement.intent == StatementIntent.MUTATION:
                mutation_result = connection.execute_workflow_sql(statement.sql)
            else:
                query_result = connection.query(statement.sql)
        except AdapterError as error:
            _emit_completed(
                emitter=emitter,
                statement=statement,
                error_message=str(error),
                written_rows=None,
                started_ns=started_ns,
            )
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
        _emit_completed(
            emitter=emitter,
            statement=statement,
            error_message=None,
            written_rows=None if mutation_result is None else mutation_result.written_rows,
            started_ns=started_ns,
        )
        results.append(
            WorkflowStatementResult(
                step_id=statement.step_id,
                query_result=query_result,
                mutation_result=mutation_result,
                error_message=None,
            )
        )
    return WorkflowExecutionResult(statement_results=tuple(results))


def _emit_completed(
    *,
    emitter: WorkflowEventEmitter | None,
    statement: WarehouseStatement,
    error_message: str | None,
    written_rows: int | None,
    started_ns: int,
) -> None:
    if emitter is None:
        return
    emitter.statement_completed(
        statement=statement,
        error_message=error_message,
        written_rows=written_rows,
        elapsed_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
    )
