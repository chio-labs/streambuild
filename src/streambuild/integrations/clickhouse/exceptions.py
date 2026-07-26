"""Clickhouse exceptions."""


class ClickHouseClientError(ValueError):
    """Raised when clickhouse input or state is invalid."""
