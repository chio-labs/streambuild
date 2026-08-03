"""Read the invocation history StreamBuild already records."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import METADATA_INVOCATIONS_TABLE_NAME

_DEFAULT_RUNS_LIMIT: int = 100


def read_runs(
    *,
    connection: AdapterConnection,
    database: str,
    limit: int = _DEFAULT_RUNS_LIMIT,
) -> list[dict[str, object]]:
    """Return recent invocations, newest first; empty when history was never written."""

    existence_query: str = (
        "SELECT count() AS present FROM system.tables "
        f"WHERE database = '{database}' AND name = '{METADATA_INVOCATIONS_TABLE_NAME}'"
    )
    present_rows: tuple = connection.query(existence_query).named_rows()
    if not present_rows or int(str(present_rows[0]["present"])) == 0:
        return []
    query: str = (
        "SELECT invocation_id, command, mode, outcome, exit_code, "
        "toString(started_at) AS started_at, toString(completed_at) AS completed_at, "
        "duration_ms, selected_node_count, error_message, tool_version "
        f"FROM `{database}`.`{METADATA_INVOCATIONS_TABLE_NAME}` "
        f"ORDER BY started_at DESC LIMIT {limit}"
    )
    runs: list[dict[str, object]] = []
    for row in connection.query(query).named_rows():
        runs.append(
            {
                "invocationId": str(row["invocation_id"]),
                "command": str(row["command"]),
                "mode": str(row["mode"]),
                "outcome": str(row["outcome"]),
                "exitCode": int(str(row["exit_code"])),
                "startedAt": str(row["started_at"]),
                "completedAt": str(row["completed_at"]),
                "durationMs": int(str(row["duration_ms"])),
                "selectedNodeCount": int(str(row["selected_node_count"])),
                "errorMessage": row["error_message"],
                "toolVersion": str(row["tool_version"]),
            }
        )
    return runs
