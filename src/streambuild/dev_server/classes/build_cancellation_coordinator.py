"""Warehouse-side cancellation for dev-server-owned build statements."""

import json

from streambuild.adapter.constants import METADATA_RUN_EVENTS_TABLE_NAME
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.models import (
    AdapterQueryCancellation,
    AdapterQueryResult,
    AdapterRunEventRecord,
)
from streambuild.dev_server.classes.warehouse_runtime import WarehouseRuntime
from streambuild.dev_server.constants import BUILD_CANCELLATION_FAILED_STATUS
from streambuild.dev_server.models import BuildCancellationOutcome
from streambuild.executor.observability.main.persist_run_events import (
    persist_run_events,
)

_CANCELLATION_EVENT_KIND: str = "cancellation_completed"
_CANCELLATION_FAILED_EVENT_KIND: str = "cancellation_failed"
_CANCELLATION_REQUESTED_EVENT_KIND: str = "cancellation_requested"


class BuildCancellationCoordinator:
    """Cancel an exact workflow query and retain the confirmed outcome."""

    def __init__(self, *, warehouse: WarehouseRuntime, database: str | None) -> None:
        self._warehouse = warehouse
        self._database = database

    def cancel_query(self, query_id: str) -> AdapterQueryCancellation:
        """Use an isolated connection so the blocked build connection is not reused."""

        with self._warehouse.read_connection() as connection:
            if connection is None:
                raise AdapterWarehouseError("Warehouse cancellation connection is unavailable")
            return connection.cancel_workflow_query(query_id=query_id)

    def record_outcome(self, outcome: BuildCancellationOutcome) -> None:
        """Append one diagnostic event after the child process has stopped."""

        if self._database is None:
            return
        with self._warehouse.read_connection() as connection:
            if connection is None:
                raise AdapterWarehouseError("Warehouse observation connection is unavailable")
            invocation_literal: str = outcome.invocation_id.replace("\\", "\\\\").replace(
                "'", "\\'"
            )
            sequence_result: AdapterQueryResult = connection.query(
                "SELECT coalesce(max(sequence), 0) + 1 AS sequence FROM "
                f"`{self._database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}` "
                f"WHERE invocation_id = '{invocation_literal}'"
            )
            sequence: int = int(str(sequence_result.rows[0][0]))
            terminal_event_kind: str = (
                _CANCELLATION_FAILED_EVENT_KIND
                if outcome.status == BUILD_CANCELLATION_FAILED_STATUS
                else _CANCELLATION_EVENT_KIND
            )
            shared_payload: dict[str, object] = {
                "queryId": outcome.query_id,
                "requestedAt": outcome.requested_at,
            }
            terminal_payload: dict[str, object] = {
                **shared_payload,
                "status": outcome.status,
                "processExitCode": outcome.process_exit_code,
                "warehouseSupported": outcome.warehouse_supported,
                "queryFound": outcome.query_found,
                "warehouseTerminationConfirmed": outcome.warehouse_termination_confirmed,
                "errorMessage": outcome.error_message,
            }
            persist_run_events(
                connection=connection,
                database=self._database,
                events=(
                    AdapterRunEventRecord(
                        invocation_id=outcome.invocation_id,
                        sequence=sequence,
                        event_kind=_CANCELLATION_REQUESTED_EVENT_KIND,
                        step_id=None,
                        phase=None,
                        payload_json=json.dumps(
                            shared_payload, sort_keys=True, separators=(",", ":"), default=str
                        ),
                    ),
                    AdapterRunEventRecord(
                        invocation_id=outcome.invocation_id,
                        sequence=sequence + 1,
                        event_kind=terminal_event_kind,
                        step_id=None,
                        phase=None,
                        payload_json=json.dumps(
                            terminal_payload, sort_keys=True, separators=(",", ":"), default=str
                        ),
                    ),
                ),
            )
