"""Timing helpers for staged backfill execution."""

from datetime import UTC, datetime
from time import sleep


def wait_for_shadow_stabilization(stabilization_seconds: float) -> None:
    """Wait briefly after live shadow creation before resolving the replay boundary."""

    if stabilization_seconds <= 0:
        return
    sleep(stabilization_seconds)


def build_current_timestamp() -> str:
    """Return the current UTC timestamp in ClickHouse-friendly string form."""

    now: datetime = datetime.now(UTC)
    return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
