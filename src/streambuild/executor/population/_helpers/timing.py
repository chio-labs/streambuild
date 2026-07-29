"""Shared stabilization and boundary-time helpers."""

import time
from datetime import UTC, datetime


def wait_for_population_stabilization(stabilization_seconds: float) -> None:
    """Wait for newly attached materialized views to receive live rows."""

    if stabilization_seconds <= 0:
        return
    time.sleep(stabilization_seconds)


def build_current_timestamp() -> str:
    """Return the current UTC timestamp in the persisted replay format."""

    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
