"""Bounded polling helpers for asynchronous ClickHouse materialization.

These wait for state the warehouse reaches asynchronously. The retry loop and
its early return are the wait condition, so unlike ordinary test helpers they
cannot be branch-free; FFT104 is excepted for this module in fensu.toml.
"""

from __future__ import annotations

import time
from typing import Any

from clickhouse_connect.driver.client import Client


def wait_for_row_count(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    expected_count: int,
    timeout_seconds: float = 25.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            f"SELECT count() FROM {clickhouse_database}.{table_name}"
        )
        actual_count: int = int(result.result_rows[0][0])
        if actual_count >= expected_count:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(
        f"Timed out waiting for {clickhouse_database}.{table_name} to reach {expected_count} rows"
    )


def wait_for_table_exists(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            "SELECT count() FROM system.tables "
            f"WHERE database = '{clickhouse_database}' AND name = '{table_name}'"
        )
        if int(result.result_rows[0][0]) > 0:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(f"Timed out waiting for {clickhouse_database}.{table_name} to exist")


def wait_for_table_missing(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            "SELECT count() FROM system.tables "
            f"WHERE database = '{clickhouse_database}' AND name = '{table_name}'"
        )
        if int(result.result_rows[0][0]) == 0:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(f"Timed out waiting for {clickhouse_database}.{table_name} to disappear")
