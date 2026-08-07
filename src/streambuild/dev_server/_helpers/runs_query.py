"""Derive run history and liveness from append-only warehouse facts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_RUN_EVENTS_TABLE_NAME,
)
from streambuild.dev_server.constants import (
    PRESUMED_FAILED_AFTER_SECONDS,
    UNRESPONSIVE_AFTER_SECONDS,
)
from streambuild.dev_server.types import RunPresentationStatus

_DEFAULT_RUNS_LIMIT: int = 100
_RUN_EVENT_PAGE_SIZE: int = 500
_RUN_EVENT_WINDOW_SIZE: int = 400
_RUN_COMPLETED_KIND: str = "run_completed"


def derive_run_status(
    *,
    terminal_outcome: str | None,
    completed_event_outcome: str | None,
    last_signal_at: datetime,
    warehouse_now: datetime,
) -> RunPresentationStatus:
    """Derive one reversible presentation status from durable facts."""

    terminal_statuses: dict[str, RunPresentationStatus] = {
        "succeeded": RunPresentationStatus.SUCCEEDED,
        "failed": RunPresentationStatus.FAILED,
        "cancelled": RunPresentationStatus.CANCELLED,
    }
    if terminal_outcome in terminal_statuses:
        return terminal_statuses[terminal_outcome]
    if completed_event_outcome in terminal_statuses:
        return terminal_statuses[completed_event_outcome]
    signal_age: float = max((warehouse_now - last_signal_at).total_seconds(), 0.0)
    if signal_age < UNRESPONSIVE_AFTER_SECONDS:
        return RunPresentationStatus.RUNNING
    if signal_age < PRESUMED_FAILED_AFTER_SECONDS:
        return RunPresentationStatus.UNRESPONSIVE
    return RunPresentationStatus.PRESUMED_FAILED


def read_runs(
    *, connection: AdapterConnection, database: str, limit: int | None = _DEFAULT_RUNS_LIMIT
) -> list[dict[str, object]]:
    """Return terminal and unterminated event streams with derived states."""

    warehouse_now: datetime = _parse_timestamp(connection.capture_warehouse_timestamp())
    terminal_by_id: dict[str, dict[str, object]] = _terminal_runs(
        connection=connection, database=database, limit=limit
    )
    streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        limit=limit,
        recent_limit=_RUN_EVENT_WINDOW_SIZE,
    )
    return _assemble_runs(
        terminal_by_id=terminal_by_id,
        streams=streams,
        warehouse_now=warehouse_now,
        limit=limit,
    )


def read_active_runs(*, connection: AdapterConnection, database: str) -> list[dict[str, object]]:
    """Return only event streams that have no durable terminal fact."""

    warehouse_now: datetime = _parse_timestamp(connection.capture_warehouse_timestamp())
    invocation_table_exists: bool = _table_exists(
        connection=connection,
        database=database,
        table=METADATA_INVOCATIONS_TABLE_NAME,
    )
    streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        recent_limit=_RUN_EVENT_WINDOW_SIZE,
        active_only=True,
        exclude_terminal_invocations=invocation_table_exists,
    )
    return _assemble_runs(
        terminal_by_id={},
        streams=streams,
        warehouse_now=warehouse_now,
        limit=None,
    )


def _assemble_runs(
    *,
    terminal_by_id: dict[str, dict[str, object]],
    streams: dict[str, list[dict[str, object]]],
    warehouse_now: datetime,
    limit: int | None,
) -> list[dict[str, object]]:
    terminal_runs: dict[str, dict[str, object]] = {
        invocation_id: dict(run) for invocation_id, run in terminal_by_id.items()
    }
    runs: list[dict[str, object]] = list(terminal_runs.values())
    invocation_id: str
    events: list[dict[str, object]]
    for invocation_id, events in streams.items():
        if invocation_id in terminal_runs:
            terminal_runs[invocation_id]["lastSignalAt"] = events[-1]["emittedAt"]
            continue
        started: dict[str, object] = events[0]
        completed: dict[str, object] | None = next(
            (event for event in reversed(events) if event["event"] == _RUN_COMPLETED_KIND), None
        )
        last_signal_at: str = str(events[-1]["emittedAt"])
        completed_outcome: str | None = None if completed is None else str(completed.get("outcome"))
        status: RunPresentationStatus = derive_run_status(
            terminal_outcome=None,
            completed_event_outcome=completed_outcome,
            last_signal_at=_parse_timestamp(last_signal_at),
            warehouse_now=warehouse_now,
        )
        started_at: str = str(started["emittedAt"])
        runs.append(
            {
                "invocationId": invocation_id,
                "command": str(started.get("command", "build")),
                "mode": str(started.get("mode", "unknown")),
                "status": str(status),
                "outcome": str(status),
                "exitCode": None if completed is None else completed.get("exitCode"),
                "startedAt": started_at,
                "completedAt": None if completed is None else completed["emittedAt"],
                "lastSignalAt": last_signal_at,
                "lastSignalAgeSeconds": _age_seconds(
                    timestamp=last_signal_at, warehouse_now=warehouse_now
                ),
                "durationMs": _age_seconds(timestamp=started_at, warehouse_now=warehouse_now)
                * 1000,
                "selectedNodeCount": int(str(started.get("selectedNodeCount", 0))),
                "errorMessage": None if completed is None else completed.get("errorMessage"),
                "toolVersion": "",
                "lastActivity": _last_activity(events=events),
            }
        )
    runs.sort(key=lambda run: str(run["startedAt"]), reverse=True)
    return runs if limit is None else runs[:limit]


def read_run_events(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_id: str,
    after: int = 0,
) -> dict[str, object]:
    """Return durable cursor events and the current derived run state."""

    warehouse_now: datetime = _parse_timestamp(connection.capture_warehouse_timestamp())
    terminal_by_id: dict[str, dict[str, object]] = _terminal_runs(
        connection=connection,
        database=database,
        invocation_id=invocation_id,
    )
    status_streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        invocation_id=invocation_id,
        recent_limit=_RUN_EVENT_WINDOW_SIZE,
    )
    runs: list[dict[str, object]] = _assemble_runs(
        terminal_by_id=terminal_by_id,
        streams=status_streams,
        warehouse_now=warehouse_now,
        limit=None,
    )
    run: dict[str, object] | None = None if not runs else runs[0]
    streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        invocation_id=invocation_id,
        after=after,
        row_limit=_RUN_EVENT_PAGE_SIZE,
    )
    return {
        "events": streams.get(invocation_id, []),
        "hasMore": len(streams.get(invocation_id, [])) == _RUN_EVENT_PAGE_SIZE,
        "status": None if run is None else run["status"],
        "lastSignalAt": None if run is None else run["lastSignalAt"],
        "lastSignalAgeSeconds": None if run is None else run["lastSignalAgeSeconds"],
    }


def _terminal_runs(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_id: str | None = None,
    limit: int | None = None,
) -> dict[str, dict[str, object]]:
    if not _table_exists(
        connection=connection, database=database, table=METADATA_INVOCATIONS_TABLE_NAME
    ):
        return {}
    where_clause: str = (
        "" if invocation_id is None else f" WHERE invocation_id = '{_sql_literal(invocation_id)}'"
    )
    limit_clause: str = "" if limit is None else f" LIMIT {limit}"
    query: str = (
        "SELECT invocation_id, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, tool_version "
        f"FROM `{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}`{where_clause} "
        f"ORDER BY started_at DESC{limit_clause}"
    )
    runs: dict[str, dict[str, object]] = {}
    for row in connection.query(query).named_rows():
        invocation_id: str = str(row["invocation_id"])
        runs[invocation_id] = {
            "invocationId": invocation_id,
            "command": str(row["command"]),
            "mode": str(row["mode"]),
            "status": str(row["outcome"]),
            "outcome": str(row["outcome"]),
            "exitCode": int(str(row["exit_code"])),
            "startedAt": str(row["started_at"]),
            "completedAt": str(row["completed_at"]),
            "lastSignalAt": str(row["completed_at"]),
            "lastSignalAgeSeconds": 0,
            "durationMs": int(str(row["duration_ms"])),
            "selectedNodeCount": int(str(row["selected_node_count"])),
            "errorMessage": row["error_message"],
            "toolVersion": str(row["tool_version"]),
            "lastActivity": None,
        }
    return runs


def _event_streams(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_id: str | None = None,
    limit: int | None = None,
    after: int = 0,
    row_limit: int | None = None,
    recent_limit: int | None = None,
    active_only: bool = False,
    exclude_terminal_invocations: bool = False,
) -> dict[str, list[dict[str, object]]]:
    if not _table_exists(
        connection=connection, database=database, table=METADATA_RUN_EVENTS_TABLE_NAME
    ):
        return {}
    clauses: list[str] = []
    if invocation_id is not None:
        clauses.append(f"invocation_id = '{_sql_literal(invocation_id)}'")
    if after:
        clauses.append(f"sequence > {after}")
    if invocation_id is None and limit is not None:
        clauses.append(
            "invocation_id IN ("
            f"SELECT invocation_id FROM `{database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}` "
            "WHERE event_kind = 'run_started' GROUP BY invocation_id "
            f"ORDER BY min(emitted_at) DESC LIMIT {limit})"
        )
    if active_only:
        clauses.append(
            "invocation_id IN ("
            f"SELECT invocation_id FROM `{database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}` "
            "GROUP BY invocation_id HAVING countIf(event_kind = 'run_started') > 0 "
            "AND countIf(event_kind = 'run_completed') = 0)"
        )
    if exclude_terminal_invocations:
        clauses.append(
            "invocation_id NOT IN ("
            f"SELECT invocation_id FROM `{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}`)"
        )
    where_clause: str = "" if not clauses else f" WHERE {' AND '.join(clauses)}"
    columns: str = (
        "invocation_id, sequence, toString(emitted_at) AS emitted_at, event_kind, "
        "step_id, phase, payload_json"
    )
    limit_clause: str = "" if row_limit is None else f" LIMIT {row_limit}"
    query: str
    if recent_limit is None:
        query = (
            f"SELECT {columns} FROM `{database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}`"
            f"{where_clause} ORDER BY invocation_id, sequence{limit_clause}"
        )
    else:
        query = (
            f"SELECT {columns} FROM (SELECT {columns}, "
            "row_number() OVER (PARTITION BY invocation_id ORDER BY sequence DESC) AS recency "
            f"FROM `{database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}`{where_clause}) "
            f"WHERE recency <= {recent_limit} OR event_kind = 'run_started' "
            "ORDER BY invocation_id, sequence"
        )
    streams: dict[str, list[dict[str, object]]] = {}
    for row in connection.query(query).named_rows():
        event_invocation_id: str = str(row["invocation_id"])
        streams.setdefault(event_invocation_id, []).append(
            {
                "sequence": int(str(row["sequence"])),
                "emittedAt": str(row["emitted_at"]),
                "event": str(row["event_kind"]),
                "stepId": row["step_id"],
                "phase": row["phase"],
                **_parsed_event_payload(row["payload_json"]),
            }
        )
    return streams


def _sql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _table_exists(*, connection: AdapterConnection, database: str, table: str) -> bool:
    query: str = (
        "SELECT count() AS present FROM system.tables "
        f"WHERE database = '{database}' AND name = '{table}'"
    )
    rows: tuple = connection.query(query).named_rows()
    return bool(rows) and int(str(rows[0]["present"])) > 0


def _parsed_event_payload(payload_json: object) -> dict[str, object]:
    try:
        parsed: object = json.loads(str(payload_json))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_timestamp(value: str) -> datetime:
    normalized: str = value.replace(" ", "T").removesuffix("Z")
    return datetime.fromisoformat(normalized).replace(tzinfo=UTC)


def _age_seconds(*, timestamp: str, warehouse_now: datetime) -> int:
    return max(int((warehouse_now - _parse_timestamp(timestamp)).total_seconds()), 0)


def _last_activity(*, events: list[dict[str, object]]) -> str | None:
    return next(
        (str(event["stepId"]) for event in reversed(events) if event.get("stepId") is not None),
        None,
    )
