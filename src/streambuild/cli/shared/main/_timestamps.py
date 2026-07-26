from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from streambuild.cli.shared.exceptions import CliUserError
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def normalize_cli_start_time(raw_value: str) -> str:
    date_formats: tuple[str, ...] = (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    date_format: str
    for date_format in date_formats:
        try:
            parsed_value: datetime = datetime.strptime(raw_value, date_format)
        except ValueError:
            continue
        if date_format == "%Y-%m-%d":
            return parsed_value.strftime("%Y-%m-%d 00:00:00.000")
        return parsed_value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    raise CliUserError(
        "--start-time must be YYYY-MM-DD or a UTC timestamp like YYYY-MM-DDTHH:MM:SS[.sss][Z]"
    )


def convert_utc_timestamp_for_clickhouse(
    *,
    client: ClickHouseClient,
    utc_timestamp: str,
) -> str:
    timezone_rows: tuple[tuple[object, ...], ...] = client.query("SELECT timezone()").rows
    if not timezone_rows:
        raise CliUserError("Could not determine ClickHouse server timezone")
    timezone_name: str = str(timezone_rows[0][0])
    parsed_timestamp: datetime = datetime.strptime(utc_timestamp, "%Y-%m-%d %H:%M:%S.%f").replace(
        tzinfo=UTC
    )
    return parsed_timestamp.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M:%S.%f")[
        :-3
    ]
