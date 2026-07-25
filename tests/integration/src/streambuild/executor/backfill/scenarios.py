from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render._helpers.create_kafka_table.main import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render._helpers.create_materialized_view.main import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table.main import render_create_table_ddl
from streambuild.compiler.compile.models import CompiledPipeline, DesiredState
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.executor.backfill.main import execute_backfill
from streambuild.executor.backfill.models import BackfillBootstrapRequest, BackfillExecutionResult
from streambuild.executor.publish.main import execute_publish
from streambuild.executor.publish.models import PublishRequest
from streambuild.integrations.clickhouse.client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill._test_types import (
    ExecuteStartTimeReplayIntegrationTestCase,
)
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_changed_offset_replay_compiled_pipeline,
    build_changed_scalar_replay_compiled_pipeline,
    build_offset_replay_compiled_pipeline,
    build_offset_replay_request,
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    require_managed_source,
)
from tests.integration.src.streambuild.executor.backfill.scenario_models import (
    StartTimeReplayScenarioResult,
)


def run_start_time_replay_scenario(
    *,
    test_case: ExecuteStartTimeReplayIntegrationTestCase,
    connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
) -> StartTimeReplayScenarioResult:
    compiled_pipeline: CompiledPipeline
    changed_desired_state: DesiredState
    timestamp_query_sql: str
    if test_case.replay_lineage_mode == "offsets":
        compiled_pipeline = build_offset_replay_compiled_pipeline()
        changed_desired_state = build_desired_state(
            (build_changed_offset_replay_compiled_pipeline(),)
        )
        timestamp_query_sql = (
            "SELECT max(_replay_landed_at) FROM "
            f"{clickhouse_database}.{{raw_table_name}} "
            f"WHERE kafka_key = '{test_case.lower_bound_source_order_id}'"
        )
    else:
        compiled_pipeline = build_scalar_replay_compiled_pipeline(test_case.replay_lineage_mode)
        changed_desired_state = build_desired_state(
            (build_changed_scalar_replay_compiled_pipeline(test_case.replay_lineage_mode),)
        )
        timestamp_query_sql = (
            "SELECT max(_replay_timestamp) FROM "
            f"{clickhouse_database}.{{raw_table_name}} "
            f"WHERE kafka_key = '{test_case.lower_bound_source_order_id}'"
        )

    clickhouse_client.command(
        render_create_kafka_table_ddl(
            require_managed_source(compiled_pipeline).kafka_table, clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            require_managed_source(compiled_pipeline).raw_table, clickhouse_database
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            require_managed_source(compiled_pipeline).materialized_view,
            clickhouse_database,
        )
    )
    clickhouse_client.insert(
        table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
        data=[
            build_raw_orders_row(
                kafka_key="historical-order",
                _replay_partition=0,
                _replay_offset=1 if test_case.replay_lineage_mode != "offsets" else 10,
                _replay_timestamp=(
                    "2026-04-09 15:59:58.000"
                    if test_case.replay_lineage_mode != "offsets"
                    else "2026-04-09 17:09:58.000"
                ),
                _replay_landed_at=(
                    "2026-04-09 15:59:58.000"
                    if test_case.replay_lineage_mode != "offsets"
                    else "2026-04-09 17:09:58.000"
                ),
            ),
            build_raw_orders_row(
                kafka_key="frontier-order",
                _replay_partition=0,
                _replay_offset=2 if test_case.replay_lineage_mode != "offsets" else 11,
                _replay_timestamp=(
                    "2026-04-09 15:59:59.000"
                    if test_case.replay_lineage_mode != "offsets"
                    else "2026-04-09 17:09:59.000"
                ),
                _replay_landed_at=(
                    "2026-04-09 15:59:59.000"
                    if test_case.replay_lineage_mode != "offsets"
                    else "2026-04-09 17:09:59.000"
                ),
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
    managed_client: ClickHouseClient = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=connection_settings.host,
            port=connection_settings.port,
            username=connection_settings.username,
            password=connection_settings.password,
            database=clickhouse_database,
        )
    )

    try:
        initial_result: BackfillExecutionResult
        if test_case.replay_lineage_mode == "offsets":
            initial_result = execute_backfill(
                build_offset_replay_request(
                    database=clickhouse_database,
                    deployment_id=test_case.initial_deployment_id,
                    created_at=test_case.created_at,
                    boundary_time=test_case.initial_boundary_time,
                ),
                managed_client,
            )
        else:
            initial_result = execute_backfill(
                build_scalar_replay_request(
                    database=clickhouse_database,
                    deployment_id=test_case.initial_deployment_id,
                    created_at=test_case.created_at,
                    boundary_time=test_case.initial_boundary_time,
                    replay_lineage_mode=test_case.replay_lineage_mode,
                ),
                managed_client,
            )
        execute_publish(
            PublishRequest(
                deployment_id=initial_result.bootstrap.deployment_id,
                metadata_database=clickhouse_database,
                default_database=clickhouse_database,
            ),
            managed_client,
        )
        frontier_timestamp: datetime = clickhouse_client.query(
            timestamp_query_sql.format(
                raw_table_name=require_managed_source(compiled_pipeline).raw_table.name
            )
        ).result_rows[0][0]
        converted_start_time: str = (
            frontier_timestamp - timedelta(milliseconds=test_case.lower_bound_offset_millis)
        ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        start_time_result: BackfillExecutionResult = execute_backfill(
            BackfillBootstrapRequest(
                desired_state=changed_desired_state,
                default_database=clickhouse_database,
                metadata_database=clickhouse_database,
                replay_lineage_mode=test_case.replay_lineage_mode,
                deployment_id=test_case.changed_deployment_id,
                created_at=test_case.created_at,
                start_time_keys=frozenset({compiled_pipeline.transforms[0].target_table.key}),
                start_time=converted_start_time,
                boundary_time=test_case.changed_boundary_time,
                stabilization_seconds=0.0,
            ),
            managed_client,
        )
        clickhouse_client.insert(
            table=f"{clickhouse_database}.{require_managed_source(compiled_pipeline).raw_table.name}",
            data=[
                build_raw_orders_row(
                    kafka_key="live-order",
                    _replay_partition=0,
                    _replay_offset=3 if test_case.replay_lineage_mode != "offsets" else 12,
                    _replay_timestamp=(
                        "2026-04-09 17:05:01.000"
                        if test_case.replay_lineage_mode != "offsets"
                        else "2026-04-09 17:15:01.000"
                    ),
                    _replay_landed_at=(
                        "2026-04-09 17:05:01.000"
                        if test_case.replay_lineage_mode != "offsets"
                        else "2026-04-09 17:15:01.000"
                    ),
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
    finally:
        managed_client.close()

    shadow_rows_result: Sequence[Sequence[object]] = clickhouse_client.query(
        "SELECT order_id, max(kafka_topic) FROM "
        f"{clickhouse_database}.{test_case.expected_shadow_table_name} "
        "GROUP BY order_id ORDER BY order_id"
    ).result_rows

    return StartTimeReplayScenarioResult(
        connection_settings=connection_settings,
        database=clickhouse_database,
        compiled_pipeline=compiled_pipeline,
        start_time_result=start_time_result,
        converted_start_time=converted_start_time,
        shadow_rows=tuple((str(row[0]), str(row[1])) for row in shadow_rows_result),
    )
