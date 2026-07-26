import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult
from clickhouse_connect.driver.client import Client

from streambuild.cli.audit.main.run_audit import run_audit
from streambuild.cli.audit_backfill.main.run_audit_backfill import run_audit_backfill
from streambuild.clickhouse.render.main.render_create_kafka_table_ddl import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render.main.render_create_materialized_view_ddl import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render.main.render_create_table_ddl import render_create_table_ddl
from streambuild.compiler.compile.main.transform_table_name import transform_table_name
from streambuild.compiler.compile.models import CompiledManagedSource, CompiledPipeline
from streambuild.compiler.shared.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.backfill.main.execute_backfill import execute_backfill
from streambuild.executor.backfill.models import BackfillExecutionResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from tests.integration.src.streambuild.cli._test_types import (
    CliAuditBackfillCommandIntegrationTestCase,
    CliAuditCommandIntegrationTestCase,
)
from tests.integration.src.streambuild.cli.helpers import (
    build_managed_clickhouse_client,
    write_audit_project_files,
    write_backfill_audit_project_files,
    write_generic_audit_project_files,
    write_multi_audit_project_files,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    require_managed_source,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliAuditCommandIntegrationTestCase(
            description="reports warning audit results against published logical tables",
            selectors=("order_items",),
            expected_exit_code=0,
            expected_output_fragments=(
                "Audit Results",
                "Warnings",
                "audits/singular/order_events/negative_line_totals.sql",
                "failing rows: 1",
                "Result: PASS (0 errors, 1 warnings)",
            ),
        ),
        CliAuditCommandIntegrationTestCase(
            description="reports generic warning audit results against published logical tables",
            selectors=("order_items",),
            expected_exit_code=0,
            expected_output_fragments=(
                "Audit Results",
                "Warnings",
                "pipelines/order_events/schema.yml  [order items order id not null]",
                "failing rows: 1",
                "Result: PASS (0 errors, 1 warnings)",
            ),
        ),
        CliAuditCommandIntegrationTestCase(
            description="reports multiple singular audits from one file with names",
            selectors=("order_items",),
            expected_exit_code=0,
            expected_output_fragments=(
                "Audit Results",
                "audits/singular/order_events/quality.sql  [negative line totals]",
                "audits/singular/order_events/quality.sql  [missing order ids]",
                "failing rows: 1",
                "Result: PASS (0 errors, 2 warnings)",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_project_when_running_live_audit_then_it_reports_expected_results(
    test_case: CliAuditCommandIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    if (
        test_case.description
        == "reports generic warning audit results against published logical tables"
    ):
        write_generic_audit_project_files(tmp_path)
    elif test_case.description == "reports multiple singular audits from one file with names":
        write_multi_audit_project_files(tmp_path)
    else:
        write_audit_project_files(tmp_path)
    clickhouse_client.command(
        (
            f"CREATE TABLE {clickhouse_database}.tbl__order_items ("
            "order_id Nullable(String), line_total Nullable(Float64)"
            ") ENGINE = MergeTree() ORDER BY tuple()"
        )
        if test_case.description
        == "reports generic warning audit results against published logical tables"
        else (
            f"CREATE TABLE {clickhouse_database}.tbl__order_items ("
            "order_id String, line_total Nullable(Float64)"
            ") ENGINE = MergeTree() ORDER BY (order_id)"
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.tbl__order_items",
        data=(
            [(None, 10.0), ("ord_002", 10.0)]
            if test_case.description
            == "reports generic warning audit results against published logical tables"
            else [("ord_001", -5.0), ("ord_missing", 10.0)]
        ),
        column_names=["order_id", "line_total"],
    )
    managed_client: ClickHouseClient = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )

    try:
        exit_code: int = run_audit(
            pipelines_root=tmp_path / "pipelines",
            project_dir=tmp_path,
            database=clickhouse_database,
            selectors=test_case.selectors,
            json_output=False,
            client=managed_client,
        )
    finally:
        managed_client.close()
    captured: CaptureResult[str] = capsys.readouterr()

    assert exit_code == test_case.expected_exit_code
    expected_output_fragment: str
    for expected_output_fragment in test_case.expected_output_fragments:
        assert expected_output_fragment in captured.out


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CliAuditBackfillCommandIntegrationTestCase(
            description="runs project sql quality checks during audit backfill",
            expected_exit_code=0,
            expected_quality_check_count=1,
            expected_assessment="not_ready",
            expected_failing_row_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_project_when_running_audit_backfill_then_it_includes_quality_checks(
    test_case: CliAuditBackfillCommandIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    deployment_id: str = "20260420T000000Z_ab12cd"
    created_at: str = "2026-04-20 00:00:00.000"
    boundary_time: str = "2026-04-20 00:00:00.000"
    write_backfill_audit_project_files(tmp_path)
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    managed_source: CompiledManagedSource = require_managed_source(compiled_pipeline)
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=managed_source.kafka_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(table=managed_source.raw_table, database=clickhouse_database)
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=managed_source.materialized_view, database=clickhouse_database
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{managed_source.raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="ord_001",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-19 23:59:59.000",
                _replay_landed_at="2026-04-19 23:59:59.000",
            )
        ],
        column_names=[
            "kafka_key",
            "kafka_value",
            "kafka_topic",
            "_replay_partition",
            "_replay_offset",
            "_replay_timestamp",
            "kafka_headers",
            "_replay_landed_at",
        ],
    )
    managed_client: ClickHouseClient = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )

    try:
        backfill_result: BackfillExecutionResult = execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id=deployment_id,
                created_at=created_at,
                boundary_time=boundary_time,
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        staged_table_name: str = build_deployment_physical_name(
            logical_name=transform_table_name("orders_enriched"),
            deployment_id=backfill_result.bootstrap.deployment_id,
        )
        clickhouse_client.command(
            f"ALTER TABLE {clickhouse_database}.{staged_table_name} "
            "UPDATE _replay_timestamp = toDateTime64('2026-04-19 23:59:59.000', 3) WHERE 1"
        )
        exit_code: int = run_audit_backfill(
            pipelines_root=tmp_path / "pipelines",
            project_dir=tmp_path,
            database=clickhouse_database,
            metadata_database=None,
            deployment_id=deployment_id,
            json_output=True,
            client=managed_client,
        )
    finally:
        managed_client.close()
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)

    assert exit_code == test_case.expected_exit_code
    assert payload["assessment"] == test_case.expected_assessment
    quality_check_results: list[dict[str, object]] = payload["quality_check_results"]  # type: ignore[assignment]
    assert len(quality_check_results) == test_case.expected_quality_check_count
    assert quality_check_results[0]["failing_row_count"] == test_case.expected_failing_row_count
