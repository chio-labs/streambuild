from collections.abc import Callable

from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.models import CompiledPipeline
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    render_create_kafka_table_ddl,
    render_create_materialized_view_ddl,
    render_create_table_ddl,
    render_create_view_ddl,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    execute_backfill,
    require_managed_source,
)


def _create_publish_active_view(
    *, clickhouse_client: Client, clickhouse_database: str, first_deployment_id: str
) -> None:
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name=f"tbl__orders_enriched__{first_deployment_id}",
        )
    )


def _leave_publish_active_view_absent(
    *, clickhouse_client: Client, clickhouse_database: str, first_deployment_id: str
) -> None:
    del clickhouse_client, clickhouse_database, first_deployment_id


PUBLISH_ACTIVE_VIEW_SETUP: dict[bool, Callable[..., None]] = {
    True: _create_publish_active_view,
    False: _leave_publish_active_view_absent,
}


def prepare_publish_resolution_scenario(
    *,
    connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    first_deployment_id: str,
    second_deployment_id: str,
    create_active_view: bool,
) -> AdapterConnection:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline("timestamp")
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
            "kafka_header_keys",
            "kafka_header_values",
            "_replay_landed_at",
        ],
    )
    managed_client: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=connection_settings.host,
            port=connection_settings.port,
            username=connection_settings.username,
            password=connection_settings.password,
            database=clickhouse_database,
        )
    )
    execute_backfill(
        request=build_scalar_replay_request(
            database=clickhouse_database,
            deployment_id=first_deployment_id,
            created_at="2026-04-09 22:00:00.123",
            boundary_time="2026-04-09 22:00:00.000",
            replay_lineage_mode="timestamp",
        ),
        client=managed_client,
    )
    execute_backfill(
        request=build_scalar_replay_request(
            database=clickhouse_database,
            deployment_id=second_deployment_id,
            created_at="2026-04-09 22:05:00.123",
            boundary_time="2026-04-09 22:05:00.000",
            replay_lineage_mode="timestamp",
        ),
        client=managed_client,
    )
    PUBLISH_ACTIVE_VIEW_SETUP[create_active_view](
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        first_deployment_id=first_deployment_id,
    )
    return managed_client
