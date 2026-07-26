from dataclasses import replace

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render._helpers.create_kafka_table.main import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render._helpers.create_materialized_view.main import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table.main import render_create_table_ddl
from streambuild.clickhouse.render._helpers.create_view.main import render_create_view_ddl
from streambuild.compiler.actual_state._helpers.load import load_actual_state
from streambuild.compiler.actual_state.models import ActualMaterializedView, ActualState
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.compiler.shared.models import MaterializedViewSpec
from streambuild.executor.backfill.main import execute_backfill
from streambuild.executor.publish.main import execute_publish
from streambuild.executor.publish.models import PublishRequest
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.integrations.clickhouse.client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.compiler.actual_state._test_types import (
    LoadActualStateIntegrationTestCase,
    LoadActualStateMixedRootsIntegrationTestCase,
    LoadActualStateWithConflictingMetadataIntegrationTestCase,
    LoadActualStateWithLatestObjectStateIntegrationTestCase,
    LoadActualStateWithoutMetadataIntegrationTestCase,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_named_scalar_replay_compiled_pipeline,
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    require_managed_source,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LoadActualStateIntegrationTestCase(
            description="loads greenfield state when no stable view exists",
            create_stable_view=False,
            create_physical_candidates=False,
            expected_actual_object_names=("kafka__orders", "mv__orders", "raw__orders"),
            expected_error_fragment=None,
        ),
        LoadActualStateIntegrationTestCase(
            description="loads active managed objects when stable view points at deployment table",
            create_stable_view=True,
            create_physical_candidates=True,
            expected_actual_object_names=(
                "kafka__orders",
                "mv__orders",
                "mv__orders_enriched",
                "raw__orders",
                "tbl__orders_enriched",
            ),
            expected_error_fragment=None,
        ),
        LoadActualStateIntegrationTestCase(
            description=(
                "ignores deployment-suffixed raw landing physicals without a stable raw interface"
            ),
            create_stable_view=True,
            create_physical_candidates=True,
            expected_actual_object_names=(
                "kafka__orders",
                "mv__orders_enriched",
                "tbl__orders_enriched",
            ),
            expected_error_fragment=None,
        ),
        LoadActualStateIntegrationTestCase(
            description="loads no active managed objects when view is missing but candidates exist",
            create_stable_view=False,
            create_physical_candidates=True,
            expected_actual_object_names=("kafka__orders", "mv__orders", "raw__orders"),
            expected_error_fragment=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_state_when_loading_actual_state_then_it_returns_expected_result(
    test_case: LoadActualStateIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    if (
        test_case.description
        == "ignores deployment-suffixed raw landing physicals without a stable raw interface"
    ):
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.raw__orders__dep_a "
            "(kafka_key String, kafka_value String, kafka_topic String, "
            "_replay_partition Int64, _replay_offset Int64, "
            "_replay_timestamp DateTime64(3), kafka_headers String, "
            "_replay_landed_at DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY (_replay_partition, _replay_offset)"
        )
        clickhouse_client.command(
            render_create_materialized_view_ddl(
                materialized_view=replace(
                    require_managed_source(compiled_pipeline).materialized_view,
                    key=replace(
                        require_managed_source(compiled_pipeline).materialized_view.key,
                        name="mv__orders__dep_a",
                    ),
                    spec=MaterializedViewSpec(
                        source_table_name=require_managed_source(
                            compiled_pipeline
                        ).materialized_view.source_table_name,
                        target_table_name="raw__orders__dep_a",
                        query=require_managed_source(compiled_pipeline).materialized_view.query,
                    ),
                ),
                database=clickhouse_database,
            )
        )
    else:
        clickhouse_client.command(
            render_create_table_ddl(
                table=require_managed_source(compiled_pipeline).raw_table,
                database=clickhouse_database,
            )
        )
        clickhouse_client.command(
            render_create_materialized_view_ddl(
                materialized_view=require_managed_source(compiled_pipeline).materialized_view,
                database=clickhouse_database,
            )
        )
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name=compiled_pipeline.transforms[0].target_table.name,
            target_table_name="tbl__orders_enriched__dep_a",
        )
        if False
        else render_create_table_ddl(
            table=compiled_pipeline.transforms[0].target_table, database=clickhouse_database
        )
    )
    if test_case.create_physical_candidates:
        clickhouse_client.command(
            f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched__dep_a "
            "(order_id String, _replay_timestamp DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY (order_id)"
        )
        if (
            test_case.description
            != "ignores deployment-suffixed raw landing physicals without a stable raw interface"
        ):
            clickhouse_client.command(
                f"CREATE MATERIALIZED VIEW {clickhouse_database}.mv__orders_enriched__dep_a "
                f"TO {clickhouse_database}.tbl__orders_enriched__dep_a AS "
                "SELECT CAST(kafka_key AS String) AS order_id, "
                "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
                f"FROM {clickhouse_database}.raw__orders"
            )
    if test_case.create_stable_view:
        clickhouse_client.command(f"DROP TABLE {clickhouse_database}.tbl__orders_enriched")
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__orders_enriched",
                target_table_name="tbl__orders_enriched__dep_a",
            )
        )

    managed_client: ClickHouseClient = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        actual_state: ActualState = load_actual_state(
            client=managed_client,
            desired_state=desired_state,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    assert (
        tuple(object_.name for object_ in actual_state.objects)
        == test_case.expected_actual_object_names
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LoadActualStateWithConflictingMetadataIntegrationTestCase(
            description=(
                "loads active state from the stable view even when deployment metadata "
                "points elsewhere"
            ),
            expected_actual_object_names=(
                "kafka__orders",
                "mv__orders",
                "mv__orders_enriched",
                "raw__orders",
                "tbl__orders_enriched",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_metadata_when_loading_actual_state_then_live_view_binding_wins(
    test_case: LoadActualStateWithConflictingMetadataIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
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
                _replay_timestamp="2026-04-09 18:59:59.000",
                _replay_landed_at="2026-04-09 18:59:59.000",
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
    managed_client: ClickHouseClient = ClickHouseClient.from_config(
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
                deployment_id="20260409T233000Z_ab12cd",
                created_at="2026-04-09 23:30:00.123",
                boundary_time="2026-04-09 23:30:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        execute_publish(
            request=PublishRequest(
                deployment_id="20260409T233000Z_ab12cd",
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
        clickhouse_client.command(
            "INSERT INTO "
            f"{clickhouse_database}.streambuild_deployments "
            "(deployment_id, created_at, status, replay_lineage_mode, selected_root_keys_json, "
            "warning_codes_json, prepared_object_mappings_json) VALUES "
            "('20260409T233500Z_wrong00', CAST('2026-04-09 23:35:00.123' AS DateTime64(3)), "
            "'published', '_replay_timestamp', '[]', '[]', '[]')"
        )
        actual_state: ActualState = load_actual_state(
            client=managed_client,
            desired_state=desired_state,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    assert (
        tuple(object_.name for object_ in actual_state.objects)
        == test_case.expected_actual_object_names
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LoadActualStateMixedRootsIntegrationTestCase(
            description=(
                "loads active objects only for the healthy root when another root is missing "
                "its stable view"
            ),
            create_orders_active_view=True,
            create_orders_candidates=True,
            create_customers_active_view=False,
            create_customers_candidates=True,
            create_customers_invalid_view=False,
            expected_actual_object_names=(
                "kafka__customers",
                "kafka__orders",
                "mv__customers",
                "mv__orders",
                "mv__orders_enriched",
                "raw__customers",
                "raw__orders",
                "tbl__orders_enriched",
            ),
        ),
        LoadActualStateMixedRootsIntegrationTestCase(
            description=(
                "loads active objects only for the healthy root when another root has an "
                "invalid active view"
            ),
            create_orders_active_view=True,
            create_orders_candidates=True,
            create_customers_active_view=False,
            create_customers_candidates=False,
            create_customers_invalid_view=True,
            expected_actual_object_names=(
                "kafka__customers",
                "kafka__orders",
                "mv__customers",
                "mv__orders",
                "mv__orders_enriched",
                "raw__customers",
                "raw__orders",
                "tbl__orders_enriched",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_root_clickhouse_state_when_loading_then_it_preserves_per_root_state(
    test_case: LoadActualStateMixedRootsIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    orders_pipeline: CompiledPipeline = build_named_scalar_replay_compiled_pipeline(
        replay_lineage_mode="timestamp",
        pipeline_name="orders_pipeline",
        source_name="orders",
        transform_name="orders_enriched",
        topic="source.orders.created",
    )
    customers_pipeline: CompiledPipeline = build_named_scalar_replay_compiled_pipeline(
        replay_lineage_mode="timestamp",
        pipeline_name="customers_pipeline",
        source_name="customers",
        transform_name="customers_enriched",
        topic="source.customers.created",
    )
    desired_state: DesiredState = build_desired_state((orders_pipeline, customers_pipeline))
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in (orders_pipeline, customers_pipeline):
        clickhouse_client.command(
            render_create_kafka_table_ddl(
                table=require_managed_source(compiled_pipeline).kafka_table,
                database=clickhouse_database,
            )
        )
        clickhouse_client.command(
            render_create_table_ddl(
                table=require_managed_source(compiled_pipeline).raw_table,
                database=clickhouse_database,
            )
        )
        clickhouse_client.command(
            render_create_materialized_view_ddl(
                materialized_view=require_managed_source(compiled_pipeline).materialized_view,
                database=clickhouse_database,
            )
        )
    if test_case.create_orders_candidates:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.tbl__orders_enriched__dep_a "
            "(order_id String, _replay_timestamp DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY (order_id)"
        )
        clickhouse_client.command(
            "CREATE MATERIALIZED VIEW "
            f"{clickhouse_database}.mv__orders_enriched__dep_a "
            f"TO {clickhouse_database}.tbl__orders_enriched__dep_a AS "
            "SELECT CAST(kafka_key AS String) AS order_id, "
            "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
            f"FROM {clickhouse_database}.raw__orders"
        )
    if test_case.create_customers_candidates:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.tbl__customers_enriched__dep_b "
            "(order_id String, _replay_timestamp DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY (order_id)"
        )
        clickhouse_client.command(
            "CREATE MATERIALIZED VIEW "
            f"{clickhouse_database}.mv__customers_enriched__dep_b "
            f"TO {clickhouse_database}.tbl__customers_enriched__dep_b AS "
            "SELECT CAST(kafka_key AS String) AS order_id, "
            "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
            f"FROM {clickhouse_database}.raw__customers"
        )
    if test_case.create_orders_active_view:
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__orders_enriched",
                target_table_name="tbl__orders_enriched__dep_a",
            )
        )
    if test_case.create_customers_active_view:
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__customers_enriched",
                target_table_name="tbl__customers_enriched__dep_b",
            )
        )
    if test_case.create_customers_invalid_view:
        clickhouse_client.command(
            "CREATE TABLE "
            f"{clickhouse_database}.tbl__customers_enriched_manual "
            "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
        )
        clickhouse_client.command(
            render_create_view_ddl(
                database=clickhouse_database,
                view_name="tbl__customers_enriched",
                target_table_name="tbl__customers_enriched_manual",
            )
        )

    managed_client: ClickHouseClient = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        actual_state: ActualState = load_actual_state(
            client=managed_client,
            desired_state=desired_state,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    assert (
        tuple(object_.name for object_ in actual_state.objects)
        == test_case.expected_actual_object_names
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LoadActualStateWithoutMetadataIntegrationTestCase(
            description="loads active state after deleting all metadata tables",
            drop_all_metadata_tables=True,
            expected_actual_object_names=(
                "kafka__orders",
                "mv__orders",
                "mv__orders_enriched",
                "raw__orders",
                "tbl__orders_enriched",
            ),
        ),
        LoadActualStateWithoutMetadataIntegrationTestCase(
            description="loads active state after deleting object state metadata only",
            drop_all_metadata_tables=False,
            expected_actual_object_names=(
                "kafka__orders",
                "mv__orders",
                "mv__orders_enriched",
                "raw__orders",
                "tbl__orders_enriched",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_published_state_when_metadata_is_deleted_then_load_actual_state_uses_live_clickhouse(
    test_case: LoadActualStateWithoutMetadataIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
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
                _replay_timestamp="2026-04-09 18:59:59.000",
                _replay_landed_at="2026-04-09 18:59:59.000",
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
    managed_client: ClickHouseClient = ClickHouseClient.from_config(
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
                deployment_id="20260409T225000Z_ab12cd",
                created_at="2026-04-09 22:50:00.123",
                boundary_time="2026-04-09 22:50:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        execute_publish(
            request=PublishRequest(
                deployment_id="20260409T225000Z_ab12cd",
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
        clickhouse_client.command(
            f"DROP TABLE {clickhouse_database}.streambuild_object_state_snapshots"
        )
        if test_case.drop_all_metadata_tables:
            clickhouse_client.command(f"DROP TABLE {clickhouse_database}.streambuild_deployments")
            clickhouse_client.command(
                f"DROP TABLE {clickhouse_database}.streambuild_deployment_watermarks"
            )
        actual_state: ActualState = load_actual_state(
            client=managed_client,
            desired_state=desired_state,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    assert (
        tuple(object_.name for object_ in actual_state.objects)
        == test_case.expected_actual_object_names
    )


RECONCILE_OVERRIDE_QUERY: str = (
    "SELECT CAST(kafka_key AS String) AS order_id, "
    "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp, "
    "CAST(kafka_topic AS String) AS kafka_topic FROM raw__orders"
)

ACTIVE_BASELINE_QUERY: str = (
    "SELECT CAST(kafka_key AS String) AS order_id, "
    "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp FROM raw__orders"
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        LoadActualStateWithLatestObjectStateIntegrationTestCase(
            description="reconcile object-state overrides active deployment query baseline",
            latest_record_deployment_id=(
                f"{RECONCILE_DEPLOYMENT_ID_PREFIX}20260409T225500Z_ab12cd"
            ),
            latest_record_query=RECONCILE_OVERRIDE_QUERY,
            expected_materialized_view_query=RECONCILE_OVERRIDE_QUERY,
        ),
        LoadActualStateWithLatestObjectStateIntegrationTestCase(
            description=(
                "non-reconcile latest object-state does not override active deployment query "
                "baseline"
            ),
            latest_record_deployment_id="20260409T225500Z_newdep0",
            latest_record_query=RECONCILE_OVERRIDE_QUERY,
            expected_materialized_view_query=ACTIVE_BASELINE_QUERY,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_latest_object_state_record_when_loading_then_only_reconcile_overrides_active_query(
    test_case: LoadActualStateWithLatestObjectStateIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> None:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
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
                _replay_timestamp="2026-04-09 18:59:59.000",
                _replay_landed_at="2026-04-09 18:59:59.000",
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
    managed_client: ClickHouseClient = ClickHouseClient.from_config(
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
                deployment_id="20260409T225000Z_ab12cd",
                created_at="2026-04-09 22:50:00.123",
                boundary_time="2026-04-09 22:50:00.000",
                replay_lineage_mode="timestamp",
            ),
            client=managed_client,
        )
        execute_publish(
            request=PublishRequest(
                deployment_id="20260409T225000Z_ab12cd",
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            client=managed_client,
        )
        clickhouse_client.insert(
            table=f"{clickhouse_database}.streambuild_object_state_snapshots",
            data=[
                (
                    test_case.latest_record_deployment_id,
                    None,
                    "materialized_view",
                    "mv__orders_enriched",
                    "reconcile_fp",
                    test_case.latest_record_query,
                    "2026-04-09 22:55:00.123",
                )
            ],
            column_names=[
                "deployment_id",
                "database_name",
                "object_type",
                "object_name",
                "normalized_fingerprint",
                "normalized_query",
                "recorded_at",
            ],
        )
        actual_state: ActualState = load_actual_state(
            client=managed_client,
            desired_state=desired_state,
            database=clickhouse_database,
        )
    finally:
        managed_client.close()

    actual_materialized_view_query: str = next(
        object_.query
        for object_ in actual_state.objects
        if isinstance(object_, ActualMaterializedView)
        if object_.name == "mv__orders_enriched"
    )

    assert actual_materialized_view_query == test_case.expected_materialized_view_query
