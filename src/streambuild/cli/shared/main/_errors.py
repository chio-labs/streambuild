"""CLI-facing ClickHouse error translation helpers for main commands."""

from streambuild.cli.shared.constants import (
    METADATA_TABLE_NAME_PREFIX,
    UNKNOWN_DATABASE_ERROR_MARKER,
)
from streambuild.integrations.clickhouse.constants import (
    AUTHENTICATION_FAILED_ERROR_CODE,
    AUTHENTICATION_FAILED_MESSAGE,
    UNKNOWN_TABLE_ERROR_CODE,
)


def render_expected_clickhouse_error(
    *,
    command_name: str,
    database: str,
    error: Exception,
) -> str | None:
    error_message: str = str(error)
    if (
        AUTHENTICATION_FAILED_ERROR_CODE in error_message
        or AUTHENTICATION_FAILED_MESSAGE in error_message
    ):
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                "Reason: ClickHouse rejected the supplied credentials.",
                "",
                "Check:",
                "- your ClickHouse username and password",
                "- any project or environment defaults used for this command",
            ]
        )
    if UNKNOWN_DATABASE_ERROR_MARKER in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                "Reason: the target ClickHouse database does not exist.",
                "",
                "If this is a fresh environment:",
                "- run stb backfill first",
                "",
                "If this database should already exist:",
                "- verify your ClickHouse connection and database name",
            ]
        )

    if UNKNOWN_TABLE_ERROR_CODE in error_message and METADATA_TABLE_NAME_PREFIX in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                "Reason: StreamBuild metadata tables do not exist in this database yet.",
                "",
                "If this is a fresh environment:",
                "- run stb backfill first",
            ]
        )

    if UNKNOWN_TABLE_ERROR_CODE in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                f"Reason: {error_message}",
            ]
        )

    return None
