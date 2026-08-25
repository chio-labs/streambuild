from streambuild.adapter.models import (
    AdapterQueryResult,
    AdapterRunEventRecord,
    AdapterRunStatementRecord,
)
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class RunEventRecordingConnection(RecordingAdapterConnection):
    """Renders one marker insert per event so persistence order is assertable."""

    def render_run_events(
        self,
        *,
        database: str,
        events: tuple[AdapterRunEventRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        self.run_events = (*getattr(self, "run_events", ()), *events)
        return tuple(
            f"INSERT_RUN_EVENT {database} {event.event_kind} {event.sequence};" for event in events
        )

    def render_run_statements(
        self,
        *,
        database: str,
        statements: tuple[AdapterRunStatementRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        del include_migration
        self.run_statements = statements
        return (f"INSERT_RUN_STATEMENTS {database} {len(statements)};",)

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return {
            True: AdapterQueryResult(rows=self._recorded_run_statement_rows()),
            False: AdapterQueryResult(rows=()),
        }["_streambuild_run_statements" in statement]

    def _recorded_run_statement_rows(self) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (record.statement_sequence, record.sql_sha256, record.workflow_sha256)
            for record in self.run_statements
        )


class UnsupportedRunStatementConnection(RunEventRecordingConnection):
    """Reports no durable run-statement support by rendering nothing."""

    def render_run_statements(
        self,
        *,
        database: str,
        statements: tuple[AdapterRunStatementRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        del database, statements, include_migration
        return ()


def build_replay_statement() -> WarehouseStatement:
    return WarehouseStatement(
        sequence=7,
        step_id="replay_orders",
        phase=WorkflowPhase.REPLAY,
        intent=StatementIntent.MUTATION,
        sql="INSERT INTO tbl SELECT 1;",
        display_name="Replay orders",
    )
