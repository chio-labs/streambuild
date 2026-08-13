"""Exact SQL builders for sensor state and observation stream reads."""

from __future__ import annotations

from datetime import datetime, timedelta

from streambuild.adapter.constants import (
    METADATA_INVOCATIONS_TABLE_NAME,
    METADATA_NODE_RESULTS_TABLE_NAME,
    METADATA_SENSOR_CHECKPOINTS_TABLE_NAME,
    METADATA_SENSOR_LEASES_TABLE_NAME,
    METADATA_SENSOR_OVERRIDES_TABLE_NAME,
    METADATA_SENSOR_STEPS_TABLE_NAME,
    METADATA_SENSOR_TICKS_TABLE_NAME,
)

_NODE_RESULT_COLUMNS: str = (
    "result_id, invocation_id, node_kind, node_name, binding_key, target_identity, "
    "trigger, status, severity, failure_count, completed_at, scheduled_for, error_message"
)
_INVOCATION_COLUMNS: str = (
    "invocation_id, command, mode, outcome, exit_code, target_identity, deployment_id, "
    "selected_node_count, error_message, completed_at"
)
_TICK_COLUMNS: str = (
    "tick_id, sensor_name, definition_fingerprint, kind, event_id, event_kind, attempt, "
    "status, started_at, completed_at, error_message, skip_reason, cursor"
)


def sql_literal(value: str) -> str:
    escaped: str = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def timestamp_literal(value: str) -> str:
    return f"toDateTime64({sql_literal(value)}, 3, 'UTC')"


def timestamp_text(value: object) -> str:
    """Normalize a warehouse timestamp value to millisecond text."""

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(value)


def shift_timestamp_text(*, value: str, seconds: float) -> str:
    """Shift one millisecond timestamp text by a signed number of seconds."""

    moment: datetime = datetime.fromisoformat(value)
    return (moment + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def timestamp_is_before(*, value: str, other: str) -> bool:
    """Compare two millisecond timestamp texts chronologically."""

    return datetime.fromisoformat(value) < datetime.fromisoformat(other)


def checkpoint_query(*, database: str, sensor_name: str, source: str) -> str:
    return (
        f"SELECT position_completed_at, position_result_id "
        f"FROM {database}.{METADATA_SENSOR_CHECKPOINTS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} AND source = {sql_literal(source)} "
        "ORDER BY position_completed_at DESC, position_result_id DESC LIMIT 1"
    )


def newest_node_result_position_query(*, database: str, target: str) -> str:
    return (
        f"SELECT completed_at, result_id FROM {database}.{METADATA_NODE_RESULTS_TABLE_NAME} "
        f"WHERE target_identity = {sql_literal(target)} "
        "ORDER BY completed_at DESC, result_id DESC LIMIT 1"
    )


def newest_invocation_position_query(*, database: str, target: str) -> str:
    return (
        f"SELECT completed_at, invocation_id FROM {database}.{METADATA_INVOCATIONS_TABLE_NAME} "
        f"WHERE target_identity = {sql_literal(target)} "
        "ORDER BY completed_at DESC, invocation_id DESC LIMIT 1"
    )


def node_results_after_query(
    *, database: str, target: str, completed_at: str, result_id: str, limit: int
) -> str:
    return (
        f"SELECT {_NODE_RESULT_COLUMNS} FROM {database}.{METADATA_NODE_RESULTS_TABLE_NAME} "
        f"WHERE target_identity = {sql_literal(target)} "
        f"AND (completed_at, result_id) > "
        f"({timestamp_literal(completed_at)}, {sql_literal(result_id)}) "
        f"ORDER BY completed_at, result_id LIMIT {int(limit)}"
    )


def node_result_by_id_query(*, database: str, result_id: str) -> str:
    return (
        f"SELECT {_NODE_RESULT_COLUMNS} FROM {database}.{METADATA_NODE_RESULTS_TABLE_NAME} "
        f"WHERE result_id = {sql_literal(result_id)} "
        "ORDER BY completed_at DESC LIMIT 1"
    )


def invocations_after_query(
    *, database: str, target: str, completed_at: str, invocation_id: str, limit: int
) -> str:
    return (
        f"SELECT {_INVOCATION_COLUMNS} FROM {database}.{METADATA_INVOCATIONS_TABLE_NAME} "
        f"WHERE target_identity = {sql_literal(target)} "
        f"AND (completed_at, invocation_id) > "
        f"({timestamp_literal(completed_at)}, {sql_literal(invocation_id)}) "
        f"ORDER BY completed_at, invocation_id LIMIT {int(limit)}"
    )


def invocation_by_id_query(*, database: str, invocation_id: str) -> str:
    return (
        f"SELECT {_INVOCATION_COLUMNS} FROM {database}.{METADATA_INVOCATIONS_TABLE_NAME} "
        f"WHERE invocation_id = {sql_literal(invocation_id)} "
        "ORDER BY completed_at DESC LIMIT 1"
    )


def previous_node_status_query(
    *, database: str, target: str, binding_key: str, completed_at: str, result_id: str
) -> str:
    return (
        f"SELECT status FROM {database}.{METADATA_NODE_RESULTS_TABLE_NAME} "
        f"WHERE target_identity = {sql_literal(target)} "
        f"AND binding_key = {sql_literal(binding_key)} "
        "AND status != 'deferred' "
        f"AND (completed_at, result_id) < "
        f"({timestamp_literal(completed_at)}, {sql_literal(result_id)}) "
        "ORDER BY completed_at DESC, result_id DESC LIMIT 1"
    )


def event_ticks_query(*, database: str, sensor_name: str, event_id: str) -> str:
    return (
        f"SELECT {_TICK_COLUMNS} FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} "
        f"AND event_id = {sql_literal(event_id)} "
        "ORDER BY started_at, tick_id"
    )


def sensor_ticks_query(
    *,
    database: str,
    sensor_name: str,
    limit: int,
    after: str | None = None,
    before: str | None = None,
) -> str:
    after_clause: str = "" if after is None else f"AND started_at >= {timestamp_literal(after)} "
    before_clause: str = "" if before is None else f"AND started_at <= {timestamp_literal(before)} "
    return (
        f"SELECT {_TICK_COLUMNS} FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} "
        f"{after_clause}{before_clause}"
        f"ORDER BY started_at DESC, tick_id DESC LIMIT {int(limit)}"
    )


def dead_letter_candidate_ticks_query(*, database: str) -> str:
    return (
        f"SELECT {_TICK_COLUMNS} FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        "WHERE (sensor_name, ifNull(event_id, '')) IN ("
        f"SELECT sensor_name, ifNull(event_id, '') "
        f"FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        "WHERE status = 'dead_lettered') "
        "ORDER BY started_at, tick_id"
    )


def latest_polling_tick_start_query(*, database: str, sensor_name: str) -> str:
    return (
        f"SELECT started_at FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} "
        "ORDER BY started_at DESC, tick_id DESC LIMIT 1"
    )


def latest_polling_success_query(*, database: str, sensor_name: str) -> str:
    return (
        f"SELECT started_at, completed_at, cursor "
        f"FROM {database}.{METADATA_SENSOR_TICKS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} AND status = 'succeeded' "
        "ORDER BY started_at DESC, tick_id DESC LIMIT 1"
    )


def step_markers_query(*, database: str, sensor_name: str, event_id: str, step_key: str) -> str:
    return (
        f"SELECT status, result_json, attempt "
        f"FROM {database}.{METADATA_SENSOR_STEPS_TABLE_NAME} "
        f"WHERE sensor_name = {sql_literal(sensor_name)} "
        f"AND event_id = {sql_literal(event_id)} "
        f"AND step_key = {sql_literal(step_key)} "
        "ORDER BY recorded_at, status"
    )


def override_statuses_query(*, database: str) -> str:
    return (
        "SELECT sensor_name, "
        "argMax(status, tuple(changed_at, override_id)) AS status "
        f"FROM {database}.{METADATA_SENSOR_OVERRIDES_TABLE_NAME} "
        "GROUP BY sensor_name"
    )


def current_lease_query(*, database: str, lease_name: str, now: str) -> str:
    return (
        f"SELECT owner_id FROM {database}.{METADATA_SENSOR_LEASES_TABLE_NAME} "
        f"WHERE lease_name = {sql_literal(lease_name)} "
        f"AND expires_at > {timestamp_literal(now)} "
        "ORDER BY acquired_at DESC, expires_at DESC, owner_id DESC LIMIT 1"
    )
