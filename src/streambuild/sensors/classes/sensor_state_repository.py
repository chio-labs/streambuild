"""Durable sensor state persistence and observation stream reads."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterSensorCheckpointRecord,
    AdapterSensorLeaseRecord,
    AdapterSensorOverrideRecord,
    AdapterSensorState,
    AdapterSensorStepRecord,
    AdapterSensorTickRecord,
)
from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.events.models import InvocationObservation, NodeResultObservation
from streambuild.executor.auditing.types import QualityResultStatus
from streambuild.executor.workflow.main.execute_sensor_state_workflow import (
    execute_sensor_state_workflow,
)
from streambuild.sensors._helpers import queries
from streambuild.sensors._helpers.workflow import assemble_sensor_state_workflow
from streambuild.sensors.constants import DISPATCH_LEASE_NAME
from streambuild.sensors.models import (
    PollingTickState,
    SensorStreamPosition,
    SensorTickView,
    StepMarker,
    TickAttemptState,
)
from streambuild.sensors.types import SensorOverrideStatus, SensorTickStatus

_TERMINAL_TICK_STATUSES: frozenset[str] = frozenset(
    {
        SensorTickStatus.SKIPPED,
        SensorTickStatus.SUCCEEDED,
        SensorTickStatus.FAILED,
        SensorTickStatus.DEAD_LETTERED,
    }
)
_RESOLVED_TICK_STATUSES: frozenset[str] = frozenset(
    {SensorTickStatus.SKIPPED, SensorTickStatus.SUCCEEDED, SensorTickStatus.DEAD_LETTERED}
)


class SensorStateRepository:
    """All sensor reads and writes against one metadata database."""

    def __init__(self, *, connection: AdapterConnection, database: str) -> None:
        self._connection: AdapterConnection = connection
        self._database: str = database
        self._migrated: bool = False

    def ensure_ready(self) -> None:
        """Idempotently create sensor state tables before the first read."""

        self._persist(AdapterSensorState())

    def warehouse_now(self) -> str:
        """Capture the warehouse's UTC millisecond timestamp."""

        return self._connection.capture_warehouse_timestamp()

    def read_checkpoint(self, *, sensor_name: str, source: str) -> SensorStreamPosition | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.checkpoint_query(
                database=self._database, sensor_name=sensor_name, source=source
            )
        )
        if not rows:
            return None
        return SensorStreamPosition(
            completed_at=queries.timestamp_text(rows[0]["position_completed_at"]),
            result_id=str(rows[0]["position_result_id"]),
        )

    def advance_checkpoint(
        self, *, sensor_name: str, source: str, position: SensorStreamPosition
    ) -> None:
        self._persist(
            AdapterSensorState(
                checkpoints=(
                    AdapterSensorCheckpointRecord(
                        sensor_name=sensor_name,
                        source=source,
                        position_completed_at=position.completed_at,
                        position_result_id=position.result_id,
                    ),
                )
            )
        )

    def newest_node_result_position(self, *, target: str) -> SensorStreamPosition | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.newest_node_result_position_query(database=self._database, target=target)
        )
        if not rows:
            return None
        return SensorStreamPosition(
            completed_at=queries.timestamp_text(rows[0]["completed_at"]),
            result_id=str(rows[0]["result_id"]),
        )

    def newest_invocation_position(self, *, target: str) -> SensorStreamPosition | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.newest_invocation_position_query(database=self._database, target=target)
        )
        if not rows:
            return None
        return SensorStreamPosition(
            completed_at=queries.timestamp_text(rows[0]["completed_at"]),
            result_id=str(rows[0]["invocation_id"]),
        )

    def fetch_node_results_after(
        self, *, position: SensorStreamPosition, target: str, limit: int
    ) -> tuple[NodeResultObservation, ...]:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.node_results_after_query(
                database=self._database,
                target=target,
                completed_at=position.completed_at,
                result_id=position.result_id,
                limit=limit,
            )
        )
        return tuple(_decode_node_result(row) for row in rows)

    def fetch_node_result(self, *, result_id: str) -> NodeResultObservation | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.node_result_by_id_query(database=self._database, result_id=result_id)
        )
        if not rows:
            return None
        return _decode_node_result(rows[0])

    def fetch_invocations_after(
        self, *, position: SensorStreamPosition, target: str, limit: int
    ) -> tuple[InvocationObservation, ...]:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.invocations_after_query(
                database=self._database,
                target=target,
                completed_at=position.completed_at,
                invocation_id=position.result_id,
                limit=limit,
            )
        )
        return tuple(_decode_invocation(row) for row in rows)

    def fetch_invocation(self, *, invocation_id: str) -> InvocationObservation | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.invocation_by_id_query(database=self._database, invocation_id=invocation_id)
        )
        if not rows:
            return None
        return _decode_invocation(rows[0])

    def previous_node_status(
        self, *, binding_key: str, target: str, position: SensorStreamPosition
    ) -> QualityResultStatus | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.previous_node_status_query(
                database=self._database,
                target=target,
                binding_key=binding_key,
                completed_at=position.completed_at,
                result_id=position.result_id,
            )
        )
        if not rows:
            return None
        return QualityResultStatus(str(rows[0]["status"]))

    def record_ticks(self, *, ticks: tuple[AdapterSensorTickRecord, ...]) -> None:
        self._persist(AdapterSensorState(ticks=ticks))

    def tick_attempt_state(self, *, sensor_name: str, event_id: str) -> TickAttemptState:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.event_ticks_query(
                database=self._database, sensor_name=sensor_name, event_id=event_id
            )
        )
        ticks: tuple[SensorTickView, ...] = _reduce_ticks(rows)
        failed: tuple[SensorTickView, ...] = tuple(
            tick for tick in ticks if tick.status == SensorTickStatus.FAILED
        )
        last_failed: SensorTickView | None = failed[-1] if failed else None
        return TickAttemptState(
            failed_attempts=len(failed),
            last_failed_at=(
                (last_failed.completed_at or last_failed.started_at) if last_failed else None
            ),
            last_error_message=last_failed.error_message if last_failed else None,
            resolved=any(tick.status in _RESOLVED_TICK_STATUSES for tick in ticks),
        )

    def list_ticks(
        self,
        *,
        sensor_name: str,
        limit: int,
        after: str | None = None,
        before: str | None = None,
    ) -> tuple[SensorTickView, ...]:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.sensor_ticks_query(
                database=self._database,
                sensor_name=sensor_name,
                limit=limit * 2,
                after=after,
                before=before,
            )
        )
        ticks: tuple[SensorTickView, ...] = _reduce_ticks(rows)
        return tuple(reversed(ticks))[:limit]

    def list_dead_letters(self) -> tuple[SensorTickView, ...]:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.dead_letter_candidate_ticks_query(database=self._database)
        )
        by_event: dict[tuple[str, str], list[Mapping[str, object]]] = {}
        for row in rows:
            key: tuple[str, str] = (str(row["sensor_name"]), str(row["event_id"] or ""))
            by_event.setdefault(key, []).append(row)
        dead_letters: list[SensorTickView] = []
        for event_rows in by_event.values():
            ticks: tuple[SensorTickView, ...] = _reduce_ticks(tuple(event_rows))
            unresolved: bool = not any(
                tick.status in (SensorTickStatus.SUCCEEDED, SensorTickStatus.SKIPPED)
                for tick in ticks
            )
            dead: tuple[SensorTickView, ...] = tuple(
                tick for tick in ticks if tick.status == SensorTickStatus.DEAD_LETTERED
            )
            if unresolved and dead:
                dead_letters.append(dead[-1])
        return tuple(sorted(dead_letters, key=lambda tick: (tick.started_at, tick.tick_id)))

    def polling_tick_state(self, *, sensor_name: str) -> PollingTickState:
        start_rows: tuple[Mapping[str, object], ...] = self._query(
            queries.latest_polling_tick_start_query(
                database=self._database, sensor_name=sensor_name
            )
        )
        success_rows: tuple[Mapping[str, object], ...] = self._query(
            queries.latest_polling_success_query(database=self._database, sensor_name=sensor_name)
        )
        cursor: object = success_rows[0]["cursor"] if success_rows else None
        return PollingTickState(
            last_started_at=(
                queries.timestamp_text(start_rows[0]["started_at"]) if start_rows else None
            ),
            last_success_at=(
                queries.timestamp_text(success_rows[0]["completed_at"])
                if success_rows and success_rows[0]["completed_at"] is not None
                else None
            ),
            cursor=str(cursor) if cursor is not None else None,
        )

    def read_step(self, *, sensor_name: str, event_id: str, step_key: str) -> StepMarker | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.step_markers_query(
                database=self._database,
                sensor_name=sensor_name,
                event_id=event_id,
                step_key=step_key,
            )
        )
        if not rows:
            return None
        attempt: int = max(int(str(row["attempt"])) for row in rows)
        succeeded: tuple[Mapping[str, object], ...] = tuple(
            row for row in rows if str(row["status"]) == SensorTickStatus.SUCCEEDED
        )
        if succeeded:
            result_json: object = succeeded[-1]["result_json"]
            return StepMarker(
                status=str(SensorTickStatus.SUCCEEDED),
                result_json=str(result_json) if result_json is not None else None,
                attempt=attempt,
            )
        failed: tuple[Mapping[str, object], ...] = tuple(
            row for row in rows if str(row["status"]) == SensorTickStatus.FAILED
        )
        status: str = str(SensorTickStatus.FAILED) if failed else str(SensorTickStatus.STARTED)
        return StepMarker(status=status, result_json=None, attempt=attempt)

    def record_step(self, *, step: AdapterSensorStepRecord) -> None:
        self._persist(AdapterSensorState(steps=(step,)))

    def override_statuses(self) -> dict[str, SensorOverrideStatus]:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.override_statuses_query(database=self._database)
        )
        return {str(row["sensor_name"]): SensorOverrideStatus(str(row["status"])) for row in rows}

    def record_override(
        self, *, sensor_name: str, status: SensorOverrideStatus, actor: str | None
    ) -> None:
        self._persist(
            AdapterSensorState(
                overrides=(
                    AdapterSensorOverrideRecord(
                        override_id=uuid4().hex,
                        sensor_name=sensor_name,
                        status=str(status),
                        actor=actor,
                    ),
                )
            )
        )

    def apply_tick_retention(self, *, retention_days: int) -> None:
        """Delete aged ticks and steps; a zero retention keeps everything."""

        rendered: tuple[str, ...] = self._connection.render_sensor_retention_cleanup(
            database=self._database, retention_days=retention_days
        )
        if rendered:
            _ = execute_sensor_state_workflow(
                statements=assemble_sensor_state_workflow(rendered),
                connection=self._connection,
            )

    def acquire_dispatch_lease(self, *, owner_id: str, ttl_seconds: float) -> bool:
        """Best-effort warehouse-time lease so parallel dispatchers do not double-fire."""

        now: str = self.warehouse_now()
        current: str | None = self._current_lease_owner(now=now)
        if current is not None and current != owner_id:
            return False
        self._persist(
            AdapterSensorState(
                leases=(
                    AdapterSensorLeaseRecord(
                        lease_name=DISPATCH_LEASE_NAME,
                        owner_id=owner_id,
                        acquired_at=now,
                        expires_at=queries.shift_timestamp_text(value=now, seconds=ttl_seconds),
                    ),
                )
            )
        )
        return self._current_lease_owner(now=now) == owner_id

    def _current_lease_owner(self, *, now: str) -> str | None:
        rows: tuple[Mapping[str, object], ...] = self._query(
            queries.current_lease_query(
                database=self._database, lease_name=DISPATCH_LEASE_NAME, now=now
            )
        )
        if not rows:
            return None
        return str(rows[0]["owner_id"])

    def _query(self, statement: str) -> tuple[Mapping[str, object], ...]:
        return tuple(self._connection.query(statement).named_rows())

    def _persist(self, state: AdapterSensorState) -> None:
        rendered: tuple[str, ...] = self._connection.render_sensor_state(
            database=self._database, state=state, include_migration=not self._migrated
        )
        if rendered:
            _ = execute_sensor_state_workflow(
                statements=assemble_sensor_state_workflow(rendered),
                connection=self._connection,
            )
        self._migrated = True


def _decode_node_result(row: Mapping[str, object]) -> NodeResultObservation:
    scheduled_for: object = row["scheduled_for"]
    error_message: object = row["error_message"]
    severity: object = row["severity"]
    return NodeResultObservation(
        result_id=str(row["result_id"]),
        invocation_id=str(row["invocation_id"]),
        node_kind=QualityNodeKind(str(row["node_kind"])),
        node_name=str(row["node_name"]),
        binding_key=str(row["binding_key"]),
        target_identity=str(row["target_identity"]),
        trigger=str(row["trigger"]),
        status=QualityResultStatus(str(row["status"])),
        severity=str(severity) if severity is not None else None,
        failure_count=int(str(row["failure_count"])),
        completed_at=queries.timestamp_text(row["completed_at"]),
        scheduled_for=(
            queries.timestamp_text(scheduled_for) if scheduled_for is not None else None
        ),
        error_message=str(error_message) if error_message is not None else None,
    )


def _decode_invocation(row: Mapping[str, object]) -> InvocationObservation:
    mode: object = row["mode"]
    deployment_id: object = row["deployment_id"]
    error_message: object = row["error_message"]
    return InvocationObservation(
        invocation_id=str(row["invocation_id"]),
        command=str(row["command"]),
        mode=str(mode) if mode is not None else None,
        outcome=str(row["outcome"]),
        exit_code=int(str(row["exit_code"])),
        target_identity=str(row["target_identity"]),
        deployment_id=str(deployment_id) if deployment_id is not None else None,
        selected_node_count=int(str(row["selected_node_count"])),
        error_message=str(error_message) if error_message is not None else None,
        completed_at=queries.timestamp_text(row["completed_at"]),
    )


def _reduce_ticks(rows: tuple[Mapping[str, object], ...]) -> tuple[SensorTickView, ...]:
    """Collapse started and terminal rows into one view per tick, in start order."""

    by_tick: dict[str, SensorTickView] = {}
    order: list[str] = []
    for row in rows:
        view: SensorTickView = _decode_tick(row)
        existing: SensorTickView | None = by_tick.get(view.tick_id)
        if existing is None:
            by_tick[view.tick_id] = view
            order.append(view.tick_id)
            continue
        if existing.status not in _TERMINAL_TICK_STATUSES:
            by_tick[view.tick_id] = view
    ordered: list[SensorTickView] = [by_tick[tick_id] for tick_id in order]
    ordered.sort(key=lambda tick: (tick.started_at, tick.tick_id))
    return tuple(ordered)


def _decode_tick(row: Mapping[str, object]) -> SensorTickView:
    event_id: object = row["event_id"]
    event_kind: object = row["event_kind"]
    completed_at: object = row["completed_at"]
    error_message: object = row["error_message"]
    skip_reason: object = row["skip_reason"]
    cursor: object = row["cursor"]
    return SensorTickView(
        tick_id=str(row["tick_id"]),
        sensor_name=str(row["sensor_name"]),
        definition_fingerprint=str(row["definition_fingerprint"]),
        kind=str(row["kind"]),
        event_id=str(event_id) if event_id is not None else None,
        event_kind=str(event_kind) if event_kind is not None else None,
        attempt=int(str(row["attempt"])),
        status=str(row["status"]),
        started_at=queries.timestamp_text(row["started_at"]),
        completed_at=(queries.timestamp_text(completed_at) if completed_at is not None else None),
        error_message=str(error_message) if error_message is not None else None,
        skip_reason=str(skip_reason) if skip_reason is not None else None,
        cursor=str(cursor) if cursor is not None else None,
    )
