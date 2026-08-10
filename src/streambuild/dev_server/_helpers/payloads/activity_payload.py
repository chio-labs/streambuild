"""Derive explainable model activity independently of replay-lineage columns."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.dev_server.constants import ACTIVITY_WINDOW_SECONDS

_QUERY_VIEWS_LOG: str = "query_views_log"
_PART_LOG: str = "part_log"
_SUCCESS_STATUS: str = "QueryFinish"
_FAILURE_STATUSES: frozenset[str] = frozenset({"ExceptionBeforeStart", "ExceptionWhileProcessing"})


@dataclass(frozen=True)
class _ActivityObservation:
    """Raw evidence collected for one target relation inside the active window."""

    last_triggered_at: str | None = None
    last_write_at: str | None = None
    rows_written: int = 0
    latest_status: str | None = None


def read_model_activity(
    *,
    connection: AdapterConnection,
    database: str,
    relation_names: tuple[str, ...],
    captured_at: str,
    active_bindings: tuple[tuple[str, str], ...] = (),
    window_seconds: int = ACTIVITY_WINDOW_SECONDS,
) -> dict[str, dict[str, object]]:
    """Return capability-aware activity evidence for every model relation."""

    unknown: dict[str, dict[str, object]] = {
        relation_name: _activity_payload(
            state="unknown",
            source="unavailable",
            source_available=False,
            approximate=False,
            window_seconds=window_seconds,
            detail="ClickHouse activity telemetry is unavailable.",
        )
        for relation_name in relation_names
    }
    try:
        capabilities: frozenset[str] = frozenset(
            str(row[0]) for row in connection.query(build_activity_capabilities_query()).rows
        )
        view_observations: dict[str, _ActivityObservation] = (
            _query_view_observations(
                connection=connection,
                database=database,
                window_seconds=window_seconds,
            )
            if _QUERY_VIEWS_LOG in capabilities
            else {}
        )
        part_observations: dict[str, _ActivityObservation] = (
            _part_log_observations(
                connection=connection,
                database=database,
                window_seconds=window_seconds,
            )
            if _PART_LOG in capabilities
            else {}
        )
        approximate_observations: dict[str, _ActivityObservation] = (
            {} if capabilities else _parts_observations(connection=connection, database=database)
        )
    except (AdapterError, KeyError, TypeError, ValueError):
        return unknown

    physical_by_logical: dict[str, str] = dict(active_bindings)
    payloads: dict[str, dict[str, object]] = {}
    for relation_name in relation_names:
        evidence_relation: str = physical_by_logical.get(relation_name, relation_name)
        view_observation: _ActivityObservation | None = view_observations.get(
            evidence_relation
        ) or view_observations.get(relation_name)
        part_observation: _ActivityObservation | None = part_observations.get(
            evidence_relation
        ) or part_observations.get(relation_name)
        approximate_observation: _ActivityObservation | None = approximate_observations.get(
            evidence_relation
        ) or approximate_observations.get(relation_name)
        if view_observation is not None:
            payloads[relation_name] = _view_activity_payload(
                observation=view_observation,
                window_seconds=window_seconds,
            )
            continue
        if part_observation is not None:
            payloads[relation_name] = _write_activity_payload(
                observation=part_observation,
                source=_PART_LOG,
                approximate=False,
                window_seconds=window_seconds,
            )
            continue
        if approximate_observation is not None:
            payloads[relation_name] = _approximate_activity_payload(
                observation=approximate_observation,
                captured_at=captured_at,
                window_seconds=window_seconds,
            )
            continue
        if capabilities:
            source: str = _QUERY_VIEWS_LOG if _QUERY_VIEWS_LOG in capabilities else _PART_LOG
            payloads[relation_name] = _activity_payload(
                state="idle",
                source=source,
                source_available=True,
                approximate=False,
                window_seconds=window_seconds,
                detail=f"No model writes were observed in the last {window_seconds}s.",
            )
            continue
        payloads[relation_name] = unknown[relation_name]
    return payloads


def build_activity_capabilities_query() -> str:
    """Inspect optional ClickHouse system-log availability."""

    return (
        "SELECT name FROM system.tables WHERE database = 'system' "
        "AND name IN ('part_log', 'query_views_log') ORDER BY name"
    )


def build_query_views_activity_query(*, database: str, window_seconds: int) -> str:
    """Read materialized-view execution evidence inside one bounded window."""

    escaped_database: str = _sql_literal(database)
    return (
        "SELECT toString(event_time_microseconds) AS observed_at, view_target, "
        "written_rows, toString(status) AS status FROM system.query_views_log "
        f"WHERE event_time >= now() - INTERVAL {window_seconds} SECOND "
        "AND view_type = 'Materialized' "
        f"AND startsWith(replaceAll(view_target, '`', ''), '{escaped_database}.') "
        "ORDER BY event_time_microseconds"
    )


def build_part_log_activity_query(*, database: str, window_seconds: int) -> str:
    """Read insert-created parts while excluding merges and mutations."""

    return (
        "SELECT toString(event_time_microseconds) AS observed_at, table, rows "
        "FROM system.part_log "
        f"WHERE database = '{_sql_literal(database)}' AND event_type = 'NewPart' "
        f"AND event_time >= now() - INTERVAL {window_seconds} SECOND "
        "ORDER BY event_time_microseconds"
    )


def build_parts_activity_query(*, database: str) -> str:
    """Approximate fallback when trustworthy activity logs are unavailable."""

    return (
        "SELECT table, toString(max(modification_time)) AS last_modified_at "
        "FROM system.parts "
        f"WHERE active AND database = '{_sql_literal(database)}' GROUP BY table ORDER BY table"
    )


def _query_view_observations(
    *, connection: AdapterConnection, database: str, window_seconds: int
) -> dict[str, _ActivityObservation]:
    observations: dict[str, _ActivityObservation] = {}
    for row in connection.query(
        build_query_views_activity_query(database=database, window_seconds=window_seconds)
    ).rows:
        event_time: str = str(row[0])
        relation_name: str = _unqualified_relation(str(row[1]))
        written_rows: int = int(str(row[2]))
        status: str = str(row[3])
        previous: _ActivityObservation = observations.get(relation_name, _ActivityObservation())
        observations[relation_name] = _ActivityObservation(
            last_triggered_at=event_time,
            last_write_at=(
                event_time
                if status == _SUCCESS_STATUS and written_rows > 0
                else previous.last_write_at
            ),
            rows_written=(
                previous.rows_written + written_rows
                if status == _SUCCESS_STATUS
                else previous.rows_written
            ),
            latest_status=status,
        )
    return observations


def _part_log_observations(
    *, connection: AdapterConnection, database: str, window_seconds: int
) -> dict[str, _ActivityObservation]:
    observations: dict[str, _ActivityObservation] = {}
    for row in connection.query(
        build_part_log_activity_query(database=database, window_seconds=window_seconds)
    ).rows:
        event_time: str = str(row[0])
        relation_name: str = str(row[1])
        written_rows: int = int(str(row[2]))
        previous: _ActivityObservation = observations.get(relation_name, _ActivityObservation())
        observations[relation_name] = _ActivityObservation(
            last_triggered_at=event_time,
            last_write_at=event_time if written_rows > 0 else previous.last_write_at,
            rows_written=previous.rows_written + written_rows,
            latest_status=_SUCCESS_STATUS,
        )
    return observations


def _parts_observations(
    *, connection: AdapterConnection, database: str
) -> dict[str, _ActivityObservation]:
    return {
        str(row[0]): _ActivityObservation(
            last_triggered_at=None,
            last_write_at=str(row[1]),
            rows_written=0,
            latest_status=_SUCCESS_STATUS,
        )
        for row in connection.query(build_parts_activity_query(database=database)).rows
    }


def _view_activity_payload(
    *, observation: _ActivityObservation, window_seconds: int
) -> dict[str, object]:
    if observation.latest_status in _FAILURE_STATUSES:
        return _activity_payload(
            state="stalled",
            source=_QUERY_VIEWS_LOG,
            source_available=True,
            approximate=False,
            window_seconds=window_seconds,
            observation=observation,
            detail="The latest materialized-view execution failed.",
        )
    return _write_activity_payload(
        observation=observation,
        source=_QUERY_VIEWS_LOG,
        approximate=False,
        window_seconds=window_seconds,
    )


def _write_activity_payload(
    *,
    observation: _ActivityObservation,
    source: str,
    approximate: bool,
    window_seconds: int,
) -> dict[str, object]:
    moving: bool = observation.rows_written > 0
    return _activity_payload(
        state="moving" if moving else "idle",
        source=source,
        source_available=True,
        approximate=approximate,
        window_seconds=window_seconds,
        observation=observation,
        detail=(
            f"{observation.rows_written} rows were written in the last {window_seconds}s."
            if moving
            else f"The model was triggered but wrote no rows in the last {window_seconds}s."
        ),
    )


def _approximate_activity_payload(
    *,
    observation: _ActivityObservation,
    captured_at: str,
    window_seconds: int,
) -> dict[str, object]:
    age_seconds: float | None = _age_seconds(
        timestamp=observation.last_write_at, captured_at=captured_at
    )
    moving: bool = age_seconds is not None and age_seconds <= window_seconds
    return _activity_payload(
        state="moving" if moving else "idle",
        source="system_parts",
        source_available=True,
        approximate=True,
        window_seconds=window_seconds,
        observation=observation,
        detail=(
            "A table part changed recently; this may include background merges."
            if moving
            else "No recent table-part modification was observed."
        ),
    )


def _activity_payload(
    *,
    state: str,
    source: str,
    source_available: bool,
    approximate: bool,
    window_seconds: int,
    detail: str,
    observation: _ActivityObservation | None = None,
) -> dict[str, object]:
    active_observation: _ActivityObservation = observation or _ActivityObservation()
    return {
        "state": state,
        "source": source,
        "sourceAvailable": source_available,
        "approximate": approximate,
        "lastTriggeredAt": active_observation.last_triggered_at,
        "lastWriteAt": active_observation.last_write_at,
        "rowsWritten": active_observation.rows_written,
        "windowSeconds": window_seconds,
        "detail": detail,
    }


def _unqualified_relation(value: str) -> str:
    return value.replace("`", "").rsplit(".", maxsplit=1)[-1]


def _age_seconds(*, timestamp: str | None, captured_at: str) -> float | None:
    if timestamp is None:
        return None
    try:
        observed_at: datetime.datetime = datetime.datetime.fromisoformat(
            timestamp.replace(" ", "T")
        )
        now_at: datetime.datetime = datetime.datetime.fromisoformat(captured_at.replace(" ", "T"))
    except ValueError:
        return None
    return max((now_at - observed_at).total_seconds(), 0.0)


def _sql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
