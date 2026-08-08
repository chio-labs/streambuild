"""Stream run events to stdout JSONL and the durable run-events table."""

from __future__ import annotations

import json
import sys
import threading
from typing import TextIO

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterRunEventRecord
from streambuild.executor.observability._helpers.payload import bounded_json
from streambuild.executor.observability._helpers.workflow import assemble_observation_workflow
from streambuild.executor.observability.constants import HEARTBEAT_INTERVAL_SECONDS
from streambuild.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement

_RUN_STARTED_KIND: str = "run_started"
_RUN_COMPLETED_KIND: str = "run_completed"
_STATEMENT_STARTED_KIND: str = "statement_started"
_STATEMENT_COMPLETED_KIND: str = "statement_completed"
_RUN_HEARTBEAT_KIND: str = "run_heartbeat"
_AUDIT_STARTED_KIND: str = "audit_started"
_AUDIT_COMPLETED_KIND: str = "audit_completed"


class RunEventSink:
    """Best-effort run narration: JSONL for pipes plus durable rows for readers."""

    def __init__(
        self,
        *,
        connection: AdapterConnection,
        database: str,
        invocation_id: str,
        jsonl_stream: TextIO | None = None,
    ) -> None:
        self._connection: AdapterConnection = connection
        self._database: str = database
        self._invocation_id: str = invocation_id
        self._jsonl_stream: TextIO | None = jsonl_stream
        self._sequence: int = 0
        self._migrated: bool = False
        self._lock: threading.Lock = threading.Lock()
        self._heartbeat_stop: threading.Event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._persistence_warning_emitted: bool = False

    def run_started(
        self, *, command: str, mode: str, total_statements: int, selected_node_count: int
    ) -> None:
        """The workflow is assembled and about to execute."""

        self._emit(
            event_kind=_RUN_STARTED_KIND,
            step_id=None,
            phase=None,
            payload={
                "command": command,
                "mode": mode,
                "totalStatements": total_statements,
                "selectedNodeCount": selected_node_count,
                "database": self._database,
            },
        )
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def run_completed(self, *, outcome: str, exit_code: int, error_message: str | None) -> None:
        """The run reached a terminal state; closes the event stream."""

        self._heartbeat_stop.set()
        heartbeat_thread: threading.Thread | None = self._heartbeat_thread
        if heartbeat_thread is not None and heartbeat_thread is not threading.current_thread():
            heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS)
        self._emit(
            event_kind=_RUN_COMPLETED_KIND,
            step_id=None,
            phase=None,
            payload={
                "outcome": outcome,
                "exitCode": exit_code,
                "errorMessage": error_message,
            },
        )

    def statement_started(self, statement: WarehouseStatement) -> None:
        """WorkflowEventEmitter: one statement is about to execute."""

        self._emit(
            event_kind=_STATEMENT_STARTED_KIND,
            step_id=statement.step_id,
            phase=str(statement.phase),
            payload={"statementSequence": statement.sequence, "intent": str(statement.intent)},
        )

    def audit_started(self, *, name: str) -> None:
        """One scheduled audit is about to execute."""

        self._emit(
            event_kind=_AUDIT_STARTED_KIND,
            step_id=name,
            phase="audit",
            payload={"name": name},
        )

    def audit_completed(
        self, *, name: str, status: str, failure_count: int, error_message: str | None
    ) -> None:
        """One scheduled audit reached a terminal result."""

        self._emit(
            event_kind=_AUDIT_COMPLETED_KIND,
            step_id=name,
            phase="audit",
            payload={
                "name": name,
                "status": status,
                "failureCount": failure_count,
                "errorMessage": error_message,
            },
        )

    def statement_completed(
        self,
        *,
        statement: WarehouseStatement,
        error_message: str | None,
        written_rows: int | None,
        elapsed_ms: int,
    ) -> None:
        """WorkflowEventEmitter: one statement finished, successfully or not."""

        self._emit(
            event_kind=_STATEMENT_COMPLETED_KIND,
            step_id=statement.step_id,
            phase=str(statement.phase),
            payload={
                "statementSequence": statement.sequence,
                "intent": str(statement.intent),
                "elapsedMs": elapsed_ms,
                "writtenRows": written_rows,
                "errorMessage": error_message,
            },
        )

    def _emit(
        self,
        *,
        event_kind: str,
        step_id: str | None,
        phase: str | None,
        payload: dict[str, object],
    ) -> None:
        with self._lock:
            self._sequence += 1
            record: AdapterRunEventRecord = AdapterRunEventRecord(
                invocation_id=self._invocation_id,
                sequence=self._sequence,
                event_kind=event_kind,
                step_id=step_id,
                phase=phase,
                payload_json=bounded_json(payload),
            )
            self._write_jsonl(record=record, payload=payload)
            self._persist(record)

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            self._emit(
                event_kind=_RUN_HEARTBEAT_KIND,
                step_id=None,
                phase=None,
                payload={},
            )

    def _write_jsonl(self, *, record: AdapterRunEventRecord, payload: dict[str, object]) -> None:
        if self._jsonl_stream is None:
            return
        line: dict[str, object] = {
            "event": record.event_kind,
            "invocationId": record.invocation_id,
            "sequence": record.sequence,
            "stepId": record.step_id,
            "phase": record.phase,
            **payload,
        }
        try:
            print(json.dumps(line, default=str), file=self._jsonl_stream, flush=True)
        except Exception:
            return

    def _persist(self, record: AdapterRunEventRecord) -> None:
        try:
            rendered: tuple[str, ...] = self._connection.render_run_events(
                database=self._database,
                events=(record,),
                include_migration=not self._migrated,
            )
            statements: tuple[WarehouseStatement, ...] = assemble_observation_workflow(rendered)
            _ = execute_observation_workflow(statements=statements, connection=self._connection)
            self._migrated = True
            self._persistence_warning_emitted = False
        except Exception as error:
            if not self._persistence_warning_emitted:
                try:
                    print(
                        f"run observation failed; continuing execution and retrying: {error}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
                self._persistence_warning_emitted = True
            return
