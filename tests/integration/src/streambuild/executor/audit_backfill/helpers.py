from collections.abc import Callable

from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.backfill.main.execute_backfill import execute_backfill
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    render_create_kafka_table_ddl,
    render_create_materialized_view_ddl,
    render_create_table_ddl,
    render_create_view_ddl,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_offset_target_insert_select_sql,
    build_raw_orders_row,
    build_scalar_replay_compiled_pipeline,
    build_scalar_replay_request,
    require_managed_source,
    require_model_resources,
)


def _create_staged_offset_materialized_view(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_model_resources(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
        .replace(
            f"{clickhouse_database}.{require_model_resources(compiled_pipeline).materialized_view.name}",
            f"{clickhouse_database}.mv__orders_enriched__{deployment_id}",
            1,
        )
        .replace(
            "TO "
            f"{clickhouse_database}."
            f"{require_model_resources(compiled_pipeline).target_table.name}",
            f"TO {clickhouse_database}.{staged_physical_name}",
            1,
        )
    )


def _leave_staged_scalar_materialized_view_absent(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    del (
        clickhouse_client,
        clickhouse_database,
        compiled_pipeline,
        deployment_id,
        staged_physical_name,
    )


STAGED_MATERIALIZED_VIEW_SETUP_BY_OFFSET_MODE: dict[bool, Callable[..., None]] = {
    True: _create_staged_offset_materialized_view,
    False: _leave_staged_scalar_materialized_view_absent,
}


def prepare_audit_staged_materialized_view(
    *,
    replay_lineage_mode: ReplayLineageMode | str,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    is_offset_mode: bool = ReplayLineageMode(replay_lineage_mode) == ReplayLineageMode.OFFSETS
    STAGED_MATERIALIZED_VIEW_SETUP_BY_OFFSET_MODE[is_offset_mode](
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        compiled_pipeline=compiled_pipeline,
        deployment_id=deployment_id,
        staged_physical_name=staged_physical_name,
    )


def _create_audit_active_view(
    *, clickhouse_client: Client, clickhouse_database: str, first_deployment_id: str
) -> None:
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name=f"tbl__orders_enriched__{first_deployment_id}",
        )
    )


def _leave_audit_active_view_absent(
    *, clickhouse_client: Client, clickhouse_database: str, first_deployment_id: str
) -> None:
    del clickhouse_client, clickhouse_database, first_deployment_id


AUDIT_ACTIVE_VIEW_SETUP: dict[bool, Callable[..., None]] = {
    True: _create_audit_active_view,
    False: _leave_audit_active_view_absent,
}


def prepare_audit_resolution_scenario(
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
                _replay_timestamp="2026-04-09 20:59:59.000",
                _replay_landed_at="2026-04-09 20:59:59.000",
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
            created_at="2026-04-09 20:00:00.123",
            boundary_time="2026-04-09 20:00:00.000",
            replay_lineage_mode="timestamp",
        ),
        client=managed_client,
    )
    execute_backfill(
        request=build_scalar_replay_request(
            database=clickhouse_database,
            deployment_id=second_deployment_id,
            created_at="2026-04-09 20:05:00.123",
            boundary_time="2026-04-09 20:05:00.000",
            replay_lineage_mode="timestamp",
        ),
        client=managed_client,
    )
    AUDIT_ACTIVE_VIEW_SETUP[create_active_view](
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        first_deployment_id=first_deployment_id,
    )
    return managed_client


def _prepare_missing_staged_partition(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    _create_staged_offset_materialized_view(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        compiled_pipeline=compiled_pipeline,
        deployment_id=deployment_id,
        staged_physical_name=staged_physical_name,
    )
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.{staged_physical_name} "
        + build_offset_target_insert_select_sql(
            database=clickhouse_database,
            source_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        )
        + " WHERE _replay_partition = 0"
    )


def _prepare_missing_source_lookup(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    del deployment_id
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.{staged_physical_name} "
        + build_offset_target_insert_select_sql(
            database=clickhouse_database,
            source_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        )
    )


def _prepare_missing_raw_rows_for_staged_offsets(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    _create_staged_offset_materialized_view(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        compiled_pipeline=compiled_pipeline,
        deployment_id=deployment_id,
        staged_physical_name=staged_physical_name,
    )
    raw_table_name: str = require_managed_source(compiled_pipeline).raw_table.name
    clickhouse_client.command(
        f"INSERT INTO {clickhouse_database}.{staged_physical_name} "
        "(order_id, _replay_partition, _replay_offset) VALUES "
        "('order-p0-historical', 0, 1), ('order-p1-live', 1, 2)"
    )
    clickhouse_client.command(
        f"ALTER TABLE {clickhouse_database}.{raw_table_name} DELETE "
        "WHERE _replay_partition = 1 AND _replay_offset = 2"
    )
    clickhouse_client.command(f"OPTIMIZE TABLE {clickhouse_database}.{raw_table_name} FINAL")


DEGRADED_OFFSET_SETUP_BY_KIND: dict[str, Callable[..., None]] = {
    "missing_staged_partition": _prepare_missing_staged_partition,
    "missing_source_lookup": _prepare_missing_source_lookup,
    "missing_raw_rows_for_staged_offsets": _prepare_missing_raw_rows_for_staged_offsets,
}


def prepare_degraded_offset_scenario(
    *,
    scenario_kind: str,
    clickhouse_client: Client,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    staged_physical_name: str,
) -> None:
    DEGRADED_OFFSET_SETUP_BY_KIND[scenario_kind](
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        compiled_pipeline=compiled_pipeline,
        deployment_id=deployment_id,
        staged_physical_name=staged_physical_name,
    )
