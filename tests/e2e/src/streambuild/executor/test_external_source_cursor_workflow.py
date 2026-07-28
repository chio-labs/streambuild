from collections.abc import Sequence
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from tests.e2e.src.streambuild.conftest import E2EClickHouseConnectionSettings
from tests.e2e.src.streambuild.executor._test_types import ExternalSourceCursorWorkflowE2ETestCase
from tests.e2e.src.streambuild.executor.helpers import (
    prepare_external_source_cursor_e2e_project,
    run_streambuild_backfill_cli,
    run_streambuild_publish_cli,
)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        ExternalSourceCursorWorkflowE2ETestCase(
            description="runs the external cursor-source workflow through publish",
            deployment_id="20260410T020000Z_cd34ef",
            expected_order_ids=("order-1", "order-2", "order-3"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_cursor_source_pipeline_when_running_then_it_publishes_expected_rows(
    test_case: ExternalSourceCursorWorkflowE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_external_source_cursor_e2e_project(tmp_path=tmp_path)
    isolated_e2e_clickhouse_client.command(
        f"CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing ("
        "order_id String, "
        "event_cursor UInt64, "
        "event_timestamp DateTime64(3)"
        ") ENGINE = MergeTree() ORDER BY (order_id)"
    )
    isolated_e2e_clickhouse_client.insert(
        table=f"{isolated_e2e_clickhouse_database}.orders_existing",
        data=[
            ("order-1", 1, "2026-04-09 16:00:01.000"),
            ("order-2", 2, "2026-04-09 16:00:02.000"),
            ("order-3", 3, "2026-04-09 16:00:03.000"),
        ],
        column_names=["order_id", "event_cursor", "event_timestamp"],
    )

    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    run_streambuild_publish_cli(
        project_dir=project_dir,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    published_rows: Sequence[Sequence[object]] = isolated_e2e_clickhouse_client.query(
        "SELECT order_id FROM "
        f"{isolated_e2e_clickhouse_database}.tbl__orders_enriched ORDER BY order_id"
    ).result_rows

    assert published_rows == [(order_id,) for order_id in test_case.expected_order_ids]
