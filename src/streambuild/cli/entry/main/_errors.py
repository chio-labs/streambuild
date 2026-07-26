"""CLI-facing warehouse error translation helpers for main commands."""

from streambuild.adapter.exceptions import (
    AdapterAuthenticationError,
    AdapterDatabaseNotFoundError,
    AdapterRelationNotFoundError,
    AdapterTimeoutError,
    AdapterWarehouseError,
)
from streambuild.cli.entry.constants import METADATA_TABLE_NAME_PREFIX


def render_expected_warehouse_error(
    *,
    command_name: str,
    database: str,
    error: AdapterWarehouseError,
) -> str | None:
    """Render an operator-facing message for an expected warehouse failure."""

    error_message: str = str(error)
    if isinstance(error, AdapterTimeoutError):
        return "\n".join(
            [
                f"{command_name.title()} could not complete",
                f"Database: {database}",
                "Reason: the ClickHouse operation timed out.",
                "",
                "Retry the command after checking warehouse availability.",
            ]
        )
    if isinstance(error, AdapterAuthenticationError):
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
    if isinstance(error, AdapterDatabaseNotFoundError):
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

    if not isinstance(error, AdapterRelationNotFoundError):
        return None

    if METADATA_TABLE_NAME_PREFIX in error_message:
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

    return "\n".join(
        [
            f"{command_name.title()} could not start",
            f"Database: {database}",
            f"Reason: {error_message}",
        ]
    )
