from streambuild.adapter.models import AdapterRunEventRecord
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


def build_replay_statement() -> WarehouseStatement:
    return WarehouseStatement(
        sequence=7,
        step_id="replay_orders",
        phase=WorkflowPhase.REPLAY,
        intent=StatementIntent.MUTATION,
        sql="INSERT INTO tbl SELECT 1;",
    )
