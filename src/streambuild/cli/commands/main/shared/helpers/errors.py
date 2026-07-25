"""CLI-facing ClickHouse error translation helpers for main commands."""


def render_expected_clickhouse_error(
    *,
    command_name: str,
    database: str,
    error: Exception,
) -> str | None:
    error_message: str = str(error)
    if "AUTHENTICATION_FAILED" in error_message or "Authentication failed" in error_message:
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
    if "UNKNOWN_DATABASE" in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                "Reason: the target ClickHouse database does not exist.",
                "",
                "If this is a fresh environment:",
                "- run streambuild backfill first",
                "",
                "If this database should already exist:",
                "- verify your ClickHouse connection and database name",
            ]
        )

    if "UNKNOWN_TABLE" in error_message and "streambuild_" in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                "Reason: StreamBuild metadata tables do not exist in this database yet.",
                "",
                "If this is a fresh environment:",
                "- run streambuild backfill first",
            ]
        )

    if "UNKNOWN_TABLE" in error_message:
        return "\n".join(
            [
                f"{command_name.title()} could not start",
                f"Database: {database}",
                f"Reason: {error_message}",
            ]
        )

    return None
