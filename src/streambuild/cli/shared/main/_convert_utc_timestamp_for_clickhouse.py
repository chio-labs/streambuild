"""Convert a UTC timestamp into ClickHouse session time."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from streambuild.cli.shared.exceptions import CliUserError
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


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
