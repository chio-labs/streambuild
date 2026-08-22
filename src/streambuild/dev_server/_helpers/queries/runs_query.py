"""Derive run history and liveness from append-only warehouse facts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import (
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_RUN_EVENTS_TABLE_NAME,
    METADATA_RUN_STATEMENTS_TABLE_NAME,
)
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterStatementProgress
from streambuild.compiler.discovery.constants import (
    DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
    RUN_UNRESPONSIVE_AFTER_SECONDS,
)
from streambuild.dev_server.types import RunPresentationStatus

_DEFAULT_RUNS_LIMIT: int = 100
_SCHEDULED_RUNS_LIMIT: int = 25
_RUN_EVENT_PAGE_SIZE: int = 500
_RUN_EVENT_WINDOW_SIZE: int = 400
_RUN_STARTED_KIND: str = "run_started"
_RUN_COMPLETED_KIND: str = "run_completed"
_STATEMENT_STARTED_KIND: str = "statement_started"
_STATEMENT_COMPLETED_KIND: str = "statement_completed"
_AUDIT_STARTED_KIND: str = "audit_started"
_AUDIT_COMPLETED_KIND: str = "audit_completed"
_AUDIT_COMMAND: str = "audit"
_SCHEDULED_MODE: str = "scheduled"
_SCHEDULED_COUNT_KEY: str = "scheduled_count"
_ERROR_COUNT_KEY: str = "error_count"
_COMPLETED_OPERATION_KINDS: frozenset[str] = frozenset(
    {_STATEMENT_COMPLETED_KIND, _AUDIT_COMPLETED_KIND}
)


def derive_run_status(
    *,
    terminal_outcome: str | None,
    completed_event_outcome: str | None,
    last_signal_at: datetime,
    warehouse_now: datetime,
    presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
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
    if signal_age < RUN_UNRESPONSIVE_AFTER_SECONDS:
        return RunPresentationStatus.RUNNING
    if signal_age < presumed_failed_after_seconds:
        return RunPresentationStatus.UNRESPONSIVE
    return RunPresentationStatus.PRESUMED_FAILED


def derive_run_duration_ms(
    *, started_at: str, completed_at: str | None, warehouse_now: datetime
) -> int:
    """Return terminal duration or current elapsed time for an active event stream."""

    duration_end: datetime = (
        warehouse_now if completed_at is None else _parse_timestamp(completed_at)
    )
    return max(int((duration_end - _parse_timestamp(started_at)).total_seconds()), 0) * 1000


def read_runs(
    *,
    connection: AdapterConnection,
    database: str,
    limit: int | None = _DEFAULT_RUNS_LIMIT,
    presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
) -> list[dict[str, object]]:
    """Return terminal and unterminated event streams with derived states."""

    warehouse_now: datetime = _parse_timestamp(connection.capture_warehouse_timestamp())
    invocation_table_exists: bool = _table_exists(
        connection=connection,
        database=database,
        table=METADATA_INVOCATIONS_TABLE_NAME,
    )
    event_table_exists: bool = _table_exists(
        connection=connection,
        database=database,
        table=METADATA_RUN_EVENTS_TABLE_NAME,
    )
    terminal_by_id: dict[str, dict[str, object]] = (
        {
            **_terminal_runs(
                connection=connection,
                database=database,
                limit=limit,
                scheduled=False,
                table_exists=True,
            ),
            **_terminal_runs(
                connection=connection,
                database=database,
                limit=_SCHEDULED_RUNS_LIMIT,
                scheduled=True,
                table_exists=True,
            ),
        }
        if invocation_table_exists
        else {}
    )
    streams: dict[str, list[dict[str, object]]] = _run_started_streams(
        connection=connection,
        database=database,
        invocation_ids=tuple(terminal_by_id),
        table_exists=event_table_exists,
    )
    active_streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        recent_limit=_RUN_EVENT_WINDOW_SIZE,
        active_only=True,
        exclude_terminal_invocations=invocation_table_exists,
        table_exists=event_table_exists,
    )
    streams.update(active_streams)
    return _assemble_runs(
        terminal_by_id=terminal_by_id,
        streams=streams,
        warehouse_now=warehouse_now,
        limit=None,
        presumed_failed_after_seconds=presumed_failed_after_seconds,
    )


def read_active_runs(
    *,
    connection: AdapterConnection,
    database: str,
    presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
) -> list[dict[str, object]]:
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
        presumed_failed_after_seconds=presumed_failed_after_seconds,
    )


def read_latest_direct_build_materialization(
    *, connection: AdapterConnection, database: str, project_identity: str
) -> str | None:
    """Return the latest terminal direct-build materialization outcome for this target."""

    if not _table_exists(
        connection=connection,
        database=database,
        table=METADATA_INVOCATIONS_TABLE_NAME,
    ):
        return None
    query: str = (
        "SELECT materialized_outcome FROM "
        f"`{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}` WHERE "
        f"{_project_identity_predicate(project_identity)} AND "
        f"target_identity = '{_sql_literal(database)}' AND command = 'build' AND mode = 'direct' "
        "AND materialized_outcome IS NOT NULL "
        "ORDER BY completed_at DESC, invocation_id DESC LIMIT 1"
    )
    rows: tuple[Mapping[str, object], ...] = connection.query(query).named_rows()
    if not rows:
        return None
    value: object = rows[0]["materialized_outcome"]
    return str(value) if value else None


def read_latest_applied_direct_build_at(
    *, connection: AdapterConnection, database: str, project_identity: str
) -> str | None:
    """Return the latest successful direct materialization completion for this target."""

    if not _table_exists(
        connection=connection,
        database=database,
        table=METADATA_INVOCATIONS_TABLE_NAME,
    ):
        return None
    query: str = (
        "SELECT toString(completed_at) AS completed_at FROM "
        f"`{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}` WHERE "
        f"{_project_identity_predicate(project_identity)} AND "
        f"target_identity = '{_sql_literal(database)}' AND command = 'build' AND mode = 'direct' "
        "AND materialized_outcome = 'applied' "
        "ORDER BY completed_at DESC, invocation_id DESC LIMIT 1"
    )
    rows: tuple[Mapping[str, object], ...] = connection.query(query).named_rows()
    return None if not rows else str(rows[0]["completed_at"])


def _assemble_runs(
    *,
    terminal_by_id: dict[str, dict[str, object]],
    streams: dict[str, list[dict[str, object]]],
    warehouse_now: datetime,
    limit: int | None,
    presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
) -> list[dict[str, object]]:
    terminal_runs: dict[str, dict[str, object]] = {
        invocation_id: dict(run) for invocation_id, run in terminal_by_id.items()
    }
    runs: list[dict[str, object]] = list(terminal_runs.values())
    invocation_id: str
    events: list[dict[str, object]]
    for invocation_id, events in streams.items():
        if invocation_id in terminal_runs:
            started: dict[str, object] | None = next(
                (event for event in events if event["event"] == _RUN_STARTED_KIND), None
            )
            if started is not None and started.get("displayCommand"):
                terminal_runs[invocation_id]["displayCommand"] = str(started["displayCommand"])
            if any(event["event"] != _RUN_STARTED_KIND for event in events):
                terminal_runs[invocation_id]["lastSignalAt"] = events[-1]["emittedAt"]
                progress: dict[str, object] = _run_progress(events=events)
                if terminal_runs[invocation_id].get("auditSummary") is not None:
                    progress.pop("auditSummary")
                terminal_runs[invocation_id].update(progress)
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
            presumed_failed_after_seconds=presumed_failed_after_seconds,
        )
        started_at: str = str(started["emittedAt"])
        runs.append(
            {
                "invocationId": invocation_id,
                "command": str(started.get("command", "build")),
                "displayCommand": str(
                    started.get("displayCommand", started.get("command", "build"))
                ),
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
                "durationMs": derive_run_duration_ms(
                    started_at=started_at,
                    completed_at=None if completed is None else str(completed["emittedAt"]),
                    warehouse_now=warehouse_now,
                ),
                "selectedNodeCount": int(str(started.get("selectedNodeCount", 0))),
                "executedLogicalIds": started.get("executedLogicalIds"),
                "contextLogicalIds": started.get("contextLogicalIds"),
                "errorMessage": None if completed is None else completed.get("errorMessage"),
                "toolVersion": str(started.get("toolVersion", "")),
                "projectIdentity": started.get("projectIdentity"),
                "lastActivity": _last_activity(events=events),
                **_run_progress(events=events),
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
    presumed_failed_after_seconds: int = DEFAULT_RUN_PRESUMED_FAILED_AFTER_SECONDS,
) -> dict[str, object]:
    """Return durable cursor events and the current derived run state."""

    warehouse_timestamp: str = connection.capture_warehouse_timestamp()
    warehouse_now: datetime = _parse_timestamp(warehouse_timestamp)
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
        presumed_failed_after_seconds=presumed_failed_after_seconds,
    )
    run: dict[str, object] | None = None if not runs else runs[0]
    streams: dict[str, list[dict[str, object]]] = _event_streams(
        connection=connection,
        database=database,
        invocation_id=invocation_id,
        after=after,
        row_limit=_RUN_EVENT_PAGE_SIZE,
    )
    events: list[dict[str, object]] = streams.get(invocation_id, [])
    return {
        "found": run is not None or bool(events),
        "events": events,
        "hasMore": len(events) == _RUN_EVENT_PAGE_SIZE,
        "status": None if run is None else run["status"],
        "lastSignalAt": None if run is None else run["lastSignalAt"],
        "lastSignalAgeSeconds": None if run is None else run["lastSignalAgeSeconds"],
        "statementProgress": _statement_progress(
            connection=connection,
            events=status_streams.get(invocation_id, []),
            observed_at=warehouse_timestamp,
        ),
    }


def _statement_progress(
    *, connection: AdapterConnection, events: list[dict[str, object]], observed_at: str
) -> dict[str, object] | None:
    active: dict[str, object] | None = _active_statement(events=events)
    if active is None or active.get("queryId") is None:
        return None
    query_id: str = str(active["queryId"])
    try:
        progress: AdapterStatementProgress | None = connection.load_statement_progress(
            query_id=query_id
        )
    except AdapterError:
        progress = None
    payload: dict[str, object] = {
        "found": progress is not None,
        "queryId": query_id,
        "statementSequence": int(str(active["statementSequence"])),
        "stepId": active.get("stepId"),
        "phase": active.get("phase"),
        "observedAt": observed_at,
    }
    if progress is None:
        return payload
    elapsed_seconds: float = progress.elapsed_seconds
    payload.update(
        {
            "elapsedSeconds": elapsed_seconds,
            "readRows": progress.read_rows,
            "readBytes": progress.read_bytes,
            "totalRowsApprox": progress.total_rows_approx,
            "memoryUsageBytes": progress.memory_usage_bytes,
            "readRowsPerSecond": (
                0.0 if elapsed_seconds <= 0 else progress.read_rows / elapsed_seconds
            ),
            "readBytesPerSecond": (
                0.0 if elapsed_seconds <= 0 else progress.read_bytes / elapsed_seconds
            ),
            "settings": dict(progress.settings),
        }
    )
    return payload


def read_run_statement(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_id: str,
    statement_sequence: int,
) -> dict[str, object]:
    """Return one lazily requested SQL statement for a durable run."""

    if not _table_exists(
        connection=connection,
        database=database,
        table=METADATA_RUN_STATEMENTS_TABLE_NAME,
    ):
        return {"found": False}
    invocation_literal: str = _sql_literal(invocation_id)
    query: str = (
        "SELECT step_id, phase, intent, sql, toString(sql_sha256) AS sql_sha256, "
        "toString(workflow_sha256) AS workflow_sha256 "
        f"FROM `{database}`.`{METADATA_RUN_STATEMENTS_TABLE_NAME}` FINAL "
        f"WHERE invocation_id = '{invocation_literal}' "
        f"AND statement_sequence = {int(statement_sequence)} LIMIT 1"
    )
    rows: tuple = connection.query(query).named_rows()
    if not rows:
        return {"found": False}
    row: Mapping[str, object] = rows[0]
    return {
        "found": True,
        "invocationId": invocation_id,
        "statementSequence": statement_sequence,
        "stepId": str(row["step_id"]),
        "phase": str(row["phase"]),
        "intent": str(row["intent"]),
        "sql": str(row["sql"]),
        "sqlSha256": str(row["sql_sha256"]),
        "workflowSha256": str(row["workflow_sha256"]),
    }


def _terminal_runs(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_id: str | None = None,
    limit: int | None = None,
    scheduled: bool | None = None,
    table_exists: bool | None = None,
) -> dict[str, dict[str, object]]:
    if table_exists is False or (
        table_exists is None
        and not _table_exists(
            connection=connection, database=database, table=METADATA_INVOCATIONS_TABLE_NAME
        )
    ):
        return {}
    clauses: list[str] = []
    if invocation_id is not None:
        clauses.append(f"invocation_id = '{_sql_literal(invocation_id)}'")
    if scheduled is True:
        clauses.append("command = 'audit' AND mode = 'scheduled'")
    elif scheduled is False:
        clauses.append("NOT (command = 'audit' AND coalesce(mode, '') = 'scheduled')")
    where_clause: str = "" if not clauses else f" WHERE {' AND '.join(clauses)}"
    limit_clause: str = "" if limit is None else f" LIMIT {limit}"
    query: str = (
        "SELECT invocation_id, project_identity, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, summary_json, tool_version "
        f"FROM `{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}`{where_clause} "
        f"ORDER BY started_at DESC{limit_clause}"
    )
    runs: dict[str, dict[str, object]] = {}
    for row in connection.query(query).named_rows():
        invocation_id: str = str(row["invocation_id"])
        runs[invocation_id] = {
            "invocationId": invocation_id,
            "projectIdentity": str(row["project_identity"]),
            "command": str(row["command"]),
            "displayCommand": None,
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
            "auditSummary": _terminal_audit_summary(
                command=str(row["command"]),
                mode=str(row["mode"]),
                summary_json=row["summary_json"],
            ),
            "toolVersion": str(row["tool_version"]),
            "lastActivity": None,
            "completedOperationCount": None,
            "totalStatements": None,
            "currentStep": None,
        }
    return runs


def _run_started_streams(
    *,
    connection: AdapterConnection,
    database: str,
    invocation_ids: tuple[str, ...],
    table_exists: bool | None = None,
) -> dict[str, list[dict[str, object]]]:
    if (
        not invocation_ids
        or table_exists is False
        or (
            table_exists is None
            and not _table_exists(
                connection=connection, database=database, table=METADATA_RUN_EVENTS_TABLE_NAME
            )
        )
    ):
        return {}
    invocation_literals: str = ", ".join(
        f"'{_sql_literal(invocation_id)}'" for invocation_id in invocation_ids
    )
    query: str = (
        "SELECT invocation_id, sequence, toString(emitted_at) AS emitted_at, event_kind, "
        "step_id, phase, payload_json "
        f"FROM `{database}`.`{METADATA_RUN_EVENTS_TABLE_NAME}` "
        f"WHERE invocation_id IN ({invocation_literals}) AND event_kind = '{_RUN_STARTED_KIND}' "
        "ORDER BY invocation_id, sequence"
    )
    return _streams_from_rows(connection.query(query).named_rows())


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
    table_exists: bool | None = None,
) -> dict[str, list[dict[str, object]]]:
    if table_exists is False or (
        table_exists is None
        and not _table_exists(
            connection=connection, database=database, table=METADATA_RUN_EVENTS_TABLE_NAME
        )
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
    return _streams_from_rows(connection.query(query).named_rows())


def _streams_from_rows(
    rows: tuple[Mapping[str, object], ...],
) -> dict[str, list[dict[str, object]]]:
    streams: dict[str, list[dict[str, object]]] = {}
    for row in rows:
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


def _project_identity_predicate(project_identity: str) -> str:
    logical_identity: str = project_identity.rsplit("/", maxsplit=1)[-1]
    literal: str = _sql_literal(logical_identity)
    suffix: str = _sql_literal(f"/{logical_identity}")
    return f"(project_identity = '{literal}' OR endsWith(project_identity, '{suffix}'))"


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


def _run_progress(*, events: list[dict[str, object]]) -> dict[str, object]:
    started: dict[str, object] | None = next(
        (event for event in events if event["event"] == _RUN_STARTED_KIND), None
    )
    raw_total: object = None if started is None else started.get("totalStatements")
    total_statements: int | None = None if raw_total is None else int(str(raw_total))
    completed_count: int = sum(event["event"] in _COMPLETED_OPERATION_KINDS for event in events)
    return {
        "completedOperationCount": completed_count,
        "totalStatements": total_statements,
        "currentStep": _active_step(events=events),
        "auditSummary": _event_audit_summary(events=events),
    }


def _terminal_audit_summary(
    *, command: str, mode: str, summary_json: object
) -> dict[str, int] | None:
    if command != _AUDIT_COMMAND or mode != _SCHEDULED_MODE:
        return None
    summary: dict[str, object] = _parsed_event_payload(summary_json)
    if _SCHEDULED_COUNT_KEY not in summary and _ERROR_COUNT_KEY not in summary:
        return None
    if summary.get(_ERROR_COUNT_KEY) is not None:
        error_count: int = int(str(summary[_ERROR_COUNT_KEY]))
        return {
            "passed": 0,
            "warning": 0,
            "failed": 0,
            "error": error_count,
            "total": error_count,
        }
    total: int = int(str(summary.get(_SCHEDULED_COUNT_KEY, 0)))
    warning: int = int(str(summary.get("warning_failure_count", 0)))
    failed: int = int(str(summary.get("error_failure_count", 0)))
    error: int = int(str(summary.get("execution_error_count", 0)))
    return {
        "passed": max(total - warning - failed - error, 0),
        "warning": warning,
        "failed": failed,
        "error": error,
        "total": total,
    }


def _event_audit_summary(*, events: list[dict[str, object]]) -> dict[str, int] | None:
    counts: dict[str, int] = {"passed": 0, "warning": 0, "failed": 0, "error": 0}
    for event in events:
        if event["event"] != _AUDIT_COMPLETED_KIND:
            continue
        status: str = str(event.get("status", ""))
        if status in counts:
            counts[status] += 1
    total: int = sum(counts.values())
    return None if total == 0 else {**counts, "total": total}


def _active_step(*, events: list[dict[str, object]]) -> str | None:
    completed_statements: dict[int, int] = {}
    completed_audits: dict[str, int] = {}
    for event in reversed(events):
        event_kind: str = str(event["event"])
        if event_kind == _STATEMENT_COMPLETED_KIND and event.get("statementSequence") is not None:
            key: int = int(str(event["statementSequence"]))
            completed_statements[key] = completed_statements.get(key, 0) + 1
        elif event_kind == _AUDIT_COMPLETED_KIND and event.get("stepId") is not None:
            audit_key: str = str(event["stepId"])
            completed_audits[audit_key] = completed_audits.get(audit_key, 0) + 1
        elif event_kind == _STATEMENT_STARTED_KIND:
            statement_key: int | None = (
                None
                if event.get("statementSequence") is None
                else int(str(event["statementSequence"]))
            )
            if statement_key is not None:
                completed_statements, consumed = _consume_count(
                    counts=completed_statements, key=statement_key
                )
                if consumed:
                    continue
            return None if event.get("stepId") is None else str(event["stepId"])
        elif event_kind == _AUDIT_STARTED_KIND:
            started_audit_key: str | None = (
                None if event.get("stepId") is None else str(event["stepId"])
            )
            if started_audit_key is not None:
                completed_audits, consumed = _consume_count(
                    counts=completed_audits, key=started_audit_key
                )
                if consumed:
                    continue
            return started_audit_key
    return None


def _active_statement(*, events: list[dict[str, object]]) -> dict[str, object] | None:
    completed_statements: dict[int, int] = {}
    for event in reversed(events):
        event_kind: str = str(event["event"])
        if event_kind == _STATEMENT_COMPLETED_KIND and event.get("statementSequence") is not None:
            key: int = int(str(event["statementSequence"]))
            completed_statements[key] = completed_statements.get(key, 0) + 1
        elif event_kind == _STATEMENT_STARTED_KIND and event.get("statementSequence") is not None:
            statement_key: int = int(str(event["statementSequence"]))
            completed_statements, consumed = _consume_count(
                counts=completed_statements, key=statement_key
            )
            if not consumed:
                return event
    return None


def _consume_count[T](*, counts: dict[T, int], key: T) -> tuple[dict[T, int], bool]:
    count: int = counts.get(key, 0)
    if count == 0:
        return counts, False
    remaining: dict[T, int] = dict(counts)
    if count == 1:
        remaining.pop(key)
    else:
        remaining[key] = count - 1
    return remaining, True
