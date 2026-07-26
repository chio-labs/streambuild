"""Convert a UTC timestamp into ClickHouse session time."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def convert_utc_timestamp_for_clickhouse(
    *,
    timezone_name: str,
    utc_timestamp: str,
) -> str:
    parsed_timestamp: datetime = datetime.strptime(utc_timestamp, "%Y-%m-%d %H:%M:%S.%f").replace(
        tzinfo=UTC
    )
    return parsed_timestamp.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M:%S.%f")[
        :-3
    ]
