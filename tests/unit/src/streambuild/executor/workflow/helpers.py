from collections.abc import Callable

from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterMutationResult, AdapterQueryResult
from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowMode, WorkflowPhase
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class RecordingWorkflowEmitter:
    """Captures emitter callbacks as flat call descriptions for exact assertions."""

    def __init__(self, *, query_id: str | None = None) -> None:
        self.calls: list[str] = []
        self.prepared_workflows: list[tuple[WarehouseStatement, ...]] = []
        self.query_id: str | None = query_id

    def workflow_prepared(
        self, *, statements: tuple[WarehouseStatement, ...], workflow_sha256: str
    ) -> None:
        self.calls.append(f"prepared:{len(statements)}:{workflow_sha256}")
        self.prepared_workflows.append(statements)

    def statement_started(self, statement: WarehouseStatement) -> str | None:
        self.calls.append(f"started:{statement.step_id}")
        return self.query_id

    def statement_completed(
        self,
        *,
        statement: WarehouseStatement,
        error_message: str | None,
        written_rows: int | None,
        elapsed_ms: int,
    ) -> None:
        self.calls.append(f"completed:{statement.step_id}:{error_message}")


class FailingPreparationEmitter(RecordingWorkflowEmitter):
    def workflow_prepared(
        self, *, statements: tuple[WarehouseStatement, ...], workflow_sha256: str
    ) -> None:
        del statements, workflow_sha256
        raise RuntimeError("statement persistence failed")


class FailingStartedWorkflowEmitter(RecordingWorkflowEmitter):
    def __init__(self, *, failed_step_id: str) -> None:
        super().__init__()
        self._failed_step_id: str = failed_step_id

    def statement_started(self, statement: WarehouseStatement) -> str | None:
        action: Callable[[WarehouseStatement], str | None] = {
            True: self._fail_started,
            False: super().statement_started,
        }[statement.step_id == self._failed_step_id]
        return action(statement)

    def _fail_started(self, statement: WarehouseStatement) -> str | None:
        del statement
        raise RuntimeError("statement started persistence failed")


class FailingCompletedWorkflowEmitter(RecordingWorkflowEmitter):
    def __init__(self, *, failed_step_id: str) -> None:
        super().__init__()
        self._failed_step_id: str = failed_step_id

    def statement_completed(
        self,
        *,
        statement: WarehouseStatement,
        error_message: str | None,
        written_rows: int | None,
        elapsed_ms: int,
    ) -> None:
        action: Callable[..., None] = {
            True: self._fail_completed,
            False: super().statement_completed,
        }[statement.step_id == self._failed_step_id]
        action(
            statement=statement,
            error_message=error_message,
            written_rows=written_rows,
            elapsed_ms=elapsed_ms,
        )

    def _fail_completed(
        self,
        *,
        statement: WarehouseStatement,
        error_message: str | None,
        written_rows: int | None,
        elapsed_ms: int,
    ) -> None:
        del statement, error_message, written_rows, elapsed_ms
        raise RuntimeError("statement completed persistence failed")


class FailingMutationConnection(RecordingAdapterConnection):
    """Every mutation fails; queries succeed — exercises the error emit path."""

    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        raise AdapterError(f"mutation rejected: {statement}")


class QueryIdRecordingConnection(RecordingAdapterConnection):
    """Capture query IDs passed through the neutral workflow execution hooks."""

    def __init__(self) -> None:
        super().__init__()
        self.query_ids: list[str | None] = []

    def execute_workflow_query(self, *, statement: str, query_id: str | None) -> AdapterQueryResult:
        self.query_ids.append(query_id)
        return self.query(statement)

    def execute_workflow_mutation(
        self, *, statement: str, query_id: str | None
    ) -> AdapterMutationResult:
        self.query_ids.append(query_id)
        return self.execute_workflow_sql(statement)


def build_tolerant_failure_workflow() -> BuildWorkflow:
    return BuildWorkflow(
        mode=WorkflowMode.DIRECT,
        plan_json='{"mode":"direct"}\n',
        statements=(
            WarehouseStatement(
                sequence=1,
                step_id="check_ready",
                phase=WorkflowPhase.PREFLIGHT,
                intent=StatementIntent.ASSERTION,
                sql="SELECT 1;",
            ),
            WarehouseStatement(
                sequence=2,
                step_id="insert_event",
                phase=WorkflowPhase.REALIZATION,
                intent=StatementIntent.MUTATION,
                sql="INSERT INTO events VALUES (1);",
                continue_on_error=True,
            ),
        ),
    )


def build_test_workflow(*, plan_json: str) -> BuildWorkflow:
    return BuildWorkflow(
        mode=WorkflowMode.DIRECT,
        plan_json=plan_json,
        statements=(
            WarehouseStatement(
                sequence=1,
                step_id="check_ready",
                phase=WorkflowPhase.PREFLIGHT,
                intent=StatementIntent.ASSERTION,
                sql="SELECT 1;",
            ),
            WarehouseStatement(
                sequence=2,
                step_id="insert_event",
                phase=WorkflowPhase.REALIZATION,
                intent=StatementIntent.MUTATION,
                sql="INSERT INTO events VALUES (1);",
            ),
        ),
    )


def build_two_mutation_workflow() -> BuildWorkflow:
    return BuildWorkflow(
        mode=WorkflowMode.DIRECT,
        plan_json='{"mode":"direct"}\n',
        statements=(
            WarehouseStatement(
                sequence=1,
                step_id="mutation_one",
                phase=WorkflowPhase.REALIZATION,
                intent=StatementIntent.MUTATION,
                sql="INSERT INTO events VALUES (1);",
            ),
            WarehouseStatement(
                sequence=2,
                step_id="mutation_two",
                phase=WorkflowPhase.REALIZATION,
                intent=StatementIntent.MUTATION,
                sql="INSERT INTO events VALUES (2);",
            ),
        ),
    )
