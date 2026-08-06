"""Publish CLI start-time normalization to external callers."""

from streambuild.cli.plan.main._normalize_cli_start_time import (
    normalize_cli_start_time as _normalize_cli_start_time,
)


def normalize_cli_start_time(raw_value: str) -> str:
    """Normalize a CLI start time into a ClickHouse millisecond timestamp."""

    return _normalize_cli_start_time(raw_value)
