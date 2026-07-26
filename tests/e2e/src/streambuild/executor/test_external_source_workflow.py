from collections.abc import Sequence
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.executor.audit_backfill.types import AuditAssessment
from tests.e2e.src.streambuild.conftest import E2EClickHouseConnectionSettings
from tests.e2e.src.streambuild.executor._test_types import ExternalSourceWorkflowE2ETestCase
from tests.e2e.src.streambuild.executor.helpers import (
    prepare_external_source_e2e_project,
    run_streambuild_audit_backfill_cli,
    run_streambuild_backfill_cli,
    run_streambuild_publish_cli,
)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        ExternalSourceWorkflowE2ETestCase(
            description="runs the external-source workflow from adopted table through publish",
            deployment_id="20260410T010000Z_ab12cd",
            expected_order_ids=("order-1", "order-2"),
            expected_audit_assessment=AuditAssessment.READY,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_source_pipeline_when_running_then_it_publishes_expected_rows(
    test_case: ExternalSourceWorkflowE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_external_source_e2e_project(tmp_path=tmp_path)
    isolated_e2e_clickhouse_client.command(
        f"CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing ("
        "order_id String, "
        "event_timestamp DateTime64(3)"
        ") ENGINE = MergeTree() ORDER BY (order_id)"
    )
    isolated_e2e_clickhouse_client.insert(
        table=f"{isolated_e2e_clickhouse_database}.orders_existing",
        data=[
            ("order-1", "2026-04-10 00:59:59.000"),
            ("order-2", "2026-04-10 00:59:59.500"),
            ("order-3", "2099-04-10 01:00:01.000"),
        ],
        column_names=["order_id", "event_timestamp"],
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
    audit_result: dict[str, object] = run_streambuild_audit_backfill_cli(
        project_dir=project_dir,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    run_streambuild_publish_cli(
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    published_rows: Sequence[Sequence[object]] = isolated_e2e_clickhouse_client.query(
        "SELECT order_id FROM "
        f"{isolated_e2e_clickhouse_database}.tbl__orders_enriched "
        "ORDER BY order_id"
    ).result_rows

    assert audit_result["assessment"] == test_case.expected_audit_assessment
    assert published_rows == [(order_id,) for order_id in test_case.expected_order_ids]
