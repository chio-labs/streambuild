"""Timing helpers for staged backfill execution."""

from datetime import UTC, datetime


def build_current_timestamp() -> str:
    """Return the current UTC timestamp in ClickHouse-friendly string form."""

    now: datetime = datetime.now(UTC)
    return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
