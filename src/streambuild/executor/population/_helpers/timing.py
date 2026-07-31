"""Shared stabilization and boundary-time helpers."""

import time


def wait_for_population_stabilization(stabilization_seconds: float) -> None:
    """Wait for newly attached materialized views to receive live rows."""

    if stabilization_seconds <= 0:
        return
    time.sleep(stabilization_seconds)
