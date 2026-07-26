from collections.abc import Sequence

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render.main.render_create_kafka_table_ddl import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render.main.render_create_materialized_view_ddl import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render.main.render_create_table_ddl import render_create_table_ddl
from streambuild.clickhouse.render.main.render_create_view_ddl import render_create_view_ddl
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.executor.backfill.main.execute_backfill import execute_backfill
from streambuild.executor.backfill.models import BackfillExecutionResult
from streambuild.executor.publish.main.execute_publish import execute_publish
from streambuild.executor.publish.models import PublishRequest, PublishResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.main.connect_clickhouse import (
    connect_clickhouse,
)
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    build_scalar_target_insert_select_sql,
    require_managed_source,
)
from tests.integration.src.streambuild.executor.publish._test_types import (
    ExecutePublishIntegrationTestCase,
    PublishAfterDeletedActiveViewIntegrationTestCase,
    PublishMissingStagedTableIntegrationTestCase,
    PublishWithoutMetadataIntegrationTestCase,
    ResolvePublishDeploymentIntegrationTestCase,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ExecutePublishIntegrationTestCase(
            description="publishes greenfield stable view for scalar replay deployment",
            replay_lineage_mode="timestamp",
            deployment_id="20260409T180000Z_ab12cd",
            created_at="2026-04-09 18:00:00.123",
            boundary_time="2026-04-09 18:00:00.000",
            expected_view_name="tbl__orders_enriched",
            expected_target_table_name="tbl__orders_enriched__20260409T180000Z_ab12cd",
            expected_published_order_ids=("historical-order", "live-order"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_greenfield_staged_deployment_when_publishing_then_it_creates_stable_view(
    test_case: ExecutePublishIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline(
        test_case.replay_lineage_mode
    )
    assert test_case.deployment_id is not None
    deployment_id: str = test_case.deployment_id
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-09 17:59:59.000",
                _replay_landed_at="2026-04-09 17:59:59.000",
            ),
            build_raw_orders_row(
                kafka_key="live-order",
                _replay_partition=0,
                _replay_offset=2,
                _replay_timestamp="2026-04-09 18:00:01.000",
                _replay_landed_at="2026-04-09 18:00:01.000",
            ),
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
    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        backfill_result: BackfillExecutionResult = execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id=deployment_id,
                created_at=test_case.created_at,
                boundary_time=test_case.boundary_time,
                replay_lineage_mode=test_case.replay_lineage_mode,
            ),
            client=managed_client,
        )
        publish_result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=deployment_id,
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    system_view_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name, engine FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name = '{test_case.expected_view_name}'"
    ).result_rows
    published_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT order_id FROM "
        f"{clickhouse_database}.{test_case.expected_view_name} "
        "ORDER BY order_id"
    ).result_rows

    assert backfill_result.bootstrap.deployment_id == deployment_id
    assert publish_result.deployment_id == deployment_id
    assert publish_result.published_views[0].view_name == test_case.expected_view_name
    assert (
        publish_result.published_views[0].target_table_name == test_case.expected_target_table_name
    )
    assert system_view_rows == [(test_case.expected_view_name, "View")]
    assert published_rows == [(order_id,) for order_id in test_case.expected_published_order_ids]


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        ResolvePublishDeploymentIntegrationTestCase(
            description="requires explicit choice with no active view and many staged deployments",
            create_active_view=False,
            first_deployment_id="20260409T220000Z_ab12cd",
            second_deployment_id="20260409T220500Z_cd34ef",
            expected_resolved_deployment_id=None,
            expected_error_fragment="Publish deployment resolution is ambiguous",
        ),
        ResolvePublishDeploymentIntegrationTestCase(
            description="auto resolves latest staged deployment newer than active view target",
            create_active_view=True,
            first_deployment_id="20260409T221000Z_ab12cd",
            second_deployment_id="20260409T221500Z_cd34ef",
            expected_resolved_deployment_id="20260409T221500Z_cd34ef",
            expected_error_fragment=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_publish_request_without_deployment_id_when_resolving_then_it_behaves_as_expected(
    test_case: ResolvePublishDeploymentIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-09 21:59:59.000",
                _replay_landed_at="2026-04-09 21:59:59.000",
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
    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id=test_case.first_deployment_id,
                created_at="2026-04-09 22:00:00.123",
                boundary_time="2026-04-09 22:00:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id=test_case.second_deployment_id,
                created_at="2026-04-09 22:05:00.123",
                boundary_time="2026-04-09 22:05:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        if test_case.create_active_view:
            clickhouse_client.command(
                render_create_view_ddl(
                    database=clickhouse_database,
                    view_name="tbl__orders_enriched",
                    target_table_name="tbl__orders_enriched__20260409T221000Z_ab12cd",
                )
            )

        if test_case.expected_error_fragment is not None:
            with pytest.raises(ValueError, match=test_case.expected_error_fragment):
                execute_publish(
                    request=PublishRequest(
                        deployment_id=None,
                        metadata_database=clickhouse_database,
                        default_database=clickhouse_database,
                    ),
                    client=managed_client,
                )
            return

        result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=None,
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    assert result.deployment_id == test_case.expected_resolved_deployment_id


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        PublishWithoutMetadataIntegrationTestCase(
            description="publishes explicit deployment after metadata deletion using live state",
            deployment_id="20260409T223000Z_ab12cd",
            expected_deployment_id="20260409T223000Z_ab12cd",
            expected_target_table_name="tbl__orders_enriched__20260409T223000Z_ab12cd",
        ),
        PublishWithoutMetadataIntegrationTestCase(
            description="resolves publish deployment after metadata deletion using live state",
            deployment_id=None,
            expected_deployment_id="20260409T223000Z_ab12cd",
            expected_target_table_name="tbl__orders_enriched__20260409T223000Z_ab12cd",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deleted_publish_metadata_when_publishing_then_it_uses_live_clickhouse_state(
    test_case: PublishWithoutMetadataIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-09 22:29:59.000",
                _replay_landed_at="2026-04-09 22:29:59.000",
            ),
            build_raw_orders_row(
                kafka_key="live-order",
                _replay_partition=0,
                _replay_offset=2,
                _replay_timestamp="2026-04-09 22:30:01.000",
                _replay_landed_at="2026-04-09 22:30:01.000",
            ),
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
    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id="20260409T223000Z_ab12cd",
                created_at="2026-04-09 22:30:00.123",
                boundary_time="2026-04-09 22:30:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        clickhouse_client.command(
            f"DROP TABLE IF EXISTS {clickhouse_database}.streambuild_deployment_watermarks"
        )
        clickhouse_client.command(
            f"DROP TABLE IF EXISTS {clickhouse_database}.streambuild_deployments"
        )
        clickhouse_client.command(
            f"DROP TABLE IF EXISTS {clickhouse_database}.streambuild_object_state_snapshots"
        )
        result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=test_case.deployment_id,
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    published_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {clickhouse_database}.tbl__orders_enriched ORDER BY order_id"
    ).result_rows

    assert result.deployment_id == test_case.expected_deployment_id
    assert result.published_views[0].target_table_name == test_case.expected_target_table_name
    assert published_rows == [("historical-order",), ("live-order",)]


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        PublishMissingStagedTableIntegrationTestCase(
            description="fails when the staged table was deleted before publish",
            deployment_id="20260409T224000Z_ab12cd",
            expected_error_fragment="has no staged physical tables to publish",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deleted_staged_table_when_publishing_then_it_fails_conservatively(
    test_case: PublishMissingStagedTableIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-09 22:39:59.000",
                _replay_landed_at="2026-04-09 22:39:59.000",
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
    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        execute_backfill(
            request=build_scalar_replay_request(
                database=clickhouse_database,
                deployment_id=test_case.deployment_id,
                created_at="2026-04-09 22:40:00.123",
                boundary_time="2026-04-09 22:40:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        clickhouse_client.command(
            f"DROP TABLE {clickhouse_database}.tbl__orders_enriched__{test_case.deployment_id}"
        )
        with pytest.raises(ValueError, match=test_case.expected_error_fragment):
            execute_publish(
                request=PublishRequest(
                    deployment_id=test_case.deployment_id,
                    metadata_database=clickhouse_database,
                    default_database=clickhouse_database,
                ),
                client=managed_client,
            )
    finally:
        managed_client.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        PublishAfterDeletedActiveViewIntegrationTestCase(
            description=(
                "publishes explicit staged deployment after the active stable view was deleted"
            ),
            active_deployment_id="20260409T223500Z_prev01",
            staged_deployment_id="20260409T224500Z_ab12cd",
            expected_target_table_name="tbl__orders_enriched__20260409T224500Z_ab12cd",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deleted_active_view_when_publishing_then_it_recreates_stable_view(
    test_case: PublishAfterDeletedActiveViewIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table, database=clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=compiled_pipeline.transforms[0].target_table, database=clickhouse_database
        ).replace(
            f"{clickhouse_database}.{compiled_pipeline.transforms[0].target_table.name}",
            (f"{clickhouse_database}.tbl__orders_enriched__{test_case.active_deployment_id}"),
            1,
        )
    )
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name=(f"tbl__orders_enriched__{test_case.active_deployment_id}"),
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1,
                _replay_timestamp="2026-04-09 22:44:59.000",
                _replay_landed_at="2026-04-09 22:44:59.000",
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
    clickhouse_client.command(
        "INSERT INTO "
        f"{clickhouse_database}.tbl__orders_enriched__{test_case.active_deployment_id} "
        + build_scalar_target_insert_select_sql(
            replay_lineage_mode="timestamp",
            database=clickhouse_database,
            source_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=compiled_pipeline.transforms[0].target_table, database=clickhouse_database
        ).replace(
            f"{clickhouse_database}.{compiled_pipeline.transforms[0].target_table.name}",
            f"{clickhouse_database}.tbl__orders_enriched__{test_case.staged_deployment_id}",
            1,
        )
    )
    clickhouse_client.command(
        "INSERT INTO "
        f"{clickhouse_database}.tbl__orders_enriched__{test_case.staged_deployment_id} "
        + build_scalar_target_insert_select_sql(
            replay_lineage_mode="timestamp",
            database=clickhouse_database,
            source_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        )
    )
    managed_client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    clickhouse_client.command(f"DROP VIEW {clickhouse_database}.tbl__orders_enriched")
    try:
        publish_result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=test_case.staged_deployment_id,
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    system_view_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT name, engine, as_select FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name = 'tbl__orders_enriched'"
    ).result_rows

    assert publish_result.deployment_id == test_case.staged_deployment_id
    assert (
        publish_result.published_views[0].target_table_name == test_case.expected_target_table_name
    )
    assert system_view_rows[0][0] == "tbl__orders_enriched"
    assert system_view_rows[0][1] == "View"
    assert str(system_view_rows[0][2]).endswith(
        f"FROM {clickhouse_database}.{test_case.expected_target_table_name}"
    )
