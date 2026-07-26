"""Build the built-in ClickHouse adapter."""

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter


def build_clickhouse_adapter() -> ClickHouseAdapter:
    """Return the ClickHouse adapter registered under the built-in adapter name."""

    return ClickHouseAdapter()
