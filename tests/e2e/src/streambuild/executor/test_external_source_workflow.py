from collections.abc import Sequence
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.audit_backfill.types import AuditAssessment
from tests.e2e.src.streambuild.conftest import E2EClickHouseConnectionSettings
from tests.e2e.src.streambuild.executor._test_types import (
    DirectExternalSourceBuildE2ETestCase,
    ExternalSourceOffsetWorkflowE2ETestCase,
    ExternalSourceWorkflowE2ETestCase,
)
from tests.e2e.src.streambuild.executor.helpers import (
    build_authored_greenfield_workflow_compiled_pipeline,
    prepare_external_source_e2e_project,
    prepare_external_source_offset_e2e_project,
    run_streambuild_audit_backfill_cli,
    run_streambuild_backfill_cli,
    run_streambuild_build_cli,
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
        f"{isolated_e2e_clickhouse_database}.tbl__orders_enriched "
        "ORDER BY order_id"
    ).result_rows

    assert audit_result["assessment"] == test_case.expected_audit_assessment
    assert published_rows == [(order_id,) for order_id in test_case.expected_order_ids]


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        ExternalSourceOffsetWorkflowE2ETestCase(
            description="runs the adopted external offset workflow through publish",
            deployment_id="20260410T013000Z_bc23de",
            expected_order_ids=("order-1", "order-2"),
            expected_watermark_rows=(("_replay_partition=0", "11"),),
            expected_replay_lineage_mode=ReplayLineageMode.OFFSETS,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_offset_source_pipeline_when_running_then_it_publishes_offset_bounded_rows(
    test_case: ExternalSourceOffsetWorkflowE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_external_source_offset_e2e_project(tmp_path=tmp_path)
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    isolated_e2e_clickhouse_client.command(
        f"CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing ("
        "order_id String, "
        "event_partition Int32, "
        "event_offset Int64, "
        "event_timestamp DateTime64(3)"
        ") ENGINE = MergeTree() ORDER BY (event_partition, event_offset)"
    )
    isolated_e2e_clickhouse_client.insert(
        table=f"{isolated_e2e_clickhouse_database}.orders_existing",
        data=[
            ("order-1", 0, 10, "2026-04-10 01:29:59.000"),
            ("order-2", 0, 11, "2026-04-10 01:29:59.500"),
            ("order-future", 0, 12, "2099-04-10 01:30:01.000"),
        ],
        column_names=["order_id", "event_partition", "event_offset", "event_timestamp"],
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
    watermark_rows: Sequence[Sequence[object]] = isolated_e2e_clickhouse_client.query(
        "SELECT boundary_key, cutoff_value FROM "
        f"{isolated_e2e_clickhouse_database}.streambuild_deployment_watermarks "
        "ORDER BY boundary_key"
    ).result_rows
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

    assert compiled_pipeline.effective_replay_lineage_mode == (
        test_case.expected_replay_lineage_mode
    )
    assert watermark_rows == list(test_case.expected_watermark_rows)
    assert published_rows == [(order_id,) for order_id in test_case.expected_order_ids]


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        DirectExternalSourceBuildE2ETestCase(
            description="runs direct build directly from adopted offset source",
            expected_order_ids=("order-1", "order-2"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_adopted_source_when_building_then_it_preserves_source_and_builds_rows(
    test_case: DirectExternalSourceBuildE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_external_source_offset_e2e_project(
        tmp_path=tmp_path, virtual_environments=False
    )
    isolated_e2e_clickhouse_client.command(
        f"CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing ("
        "order_id String, event_partition Int32, event_offset Int64, "
        "event_timestamp DateTime64(3)) "
        "ENGINE = MergeTree() ORDER BY (event_partition, event_offset)"
    )
    isolated_e2e_clickhouse_client.insert(
        table=f"{isolated_e2e_clickhouse_database}.orders_existing",
        data=[
            ("order-1", 0, 10, "2026-04-10 01:29:59.000"),
            ("order-2", 0, 11, "2026-04-10 01:29:59.500"),
        ],
        column_names=["order_id", "event_partition", "event_offset", "event_timestamp"],
    )
    source_ddl_before: str = str(
        isolated_e2e_clickhouse_client.query(
            f"SHOW CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing"
        ).result_rows[0][0]
    )

    run_streambuild_build_cli(
        project_dir=project_dir,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
    )

    source_ddl_after: str = str(
        isolated_e2e_clickhouse_client.query(
            f"SHOW CREATE TABLE {isolated_e2e_clickhouse_database}.orders_existing"
        ).result_rows[0][0]
    )
    built_rows: Sequence[Sequence[object]] = isolated_e2e_clickhouse_client.query(
        f"SELECT order_id FROM {isolated_e2e_clickhouse_database}.tbl__orders_enriched "
        "ORDER BY order_id"
    ).result_rows
    assert source_ddl_after == source_ddl_before
    assert built_rows == [(order_id,) for order_id in test_case.expected_order_ids]
