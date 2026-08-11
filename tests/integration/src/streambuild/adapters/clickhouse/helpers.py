import json
from collections.abc import Sequence
from pathlib import Path
from threading import Barrier

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterConnectionConfig,
    AdapterInvocationRecord,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
)
from streambuild.compiler.discovery._helpers.load import load_pipeline_directory
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


def render_create_kafka_table_ddl(
    *, table: DesiredKafkaTable, database: str, if_not_exists: bool = False
) -> str:
    return ClickHouseAdapter().render_resource(
        resource=build_adapter_resource(table),
        database=database,
        if_not_exists=if_not_exists,
    )


def render_create_table_ddl(*, table: DesiredTable, database: str) -> str:
    return ClickHouseAdapter().render_resource(
        resource=build_adapter_resource(table),
        database=database,
    )


def render_adapter_table_ddl(*, table: AdapterTable, database: str) -> str:
    return ClickHouseAdapter().render_resource(resource=table, database=database)


def render_create_materialized_view_ddl(
    *, materialized_view: DesiredMaterializedView, database: str
) -> str:
    return ClickHouseAdapter().render_resource(
        resource=build_adapter_resource(materialized_view),
        database=database,
    )


def render_adapter_materialized_view_ddl(
    *, materialized_view: AdapterMaterializedView, database: str
) -> str:
    return ClickHouseAdapter().render_resource(resource=materialized_view, database=database)


def render_create_view_ddl(*, database: str, view_name: str, target_table_name: str) -> str:
    return ClickHouseAdapter().render_resource(
        resource=AdapterStableView(name=view_name, target_relation_name=target_table_name),
        database=database,
    )


def build_compiled_example_pipeline() -> CompiledPipeline:
    return compile_pipeline(
        loaded_pipeline=load_pipeline_directory(
            Path("tests/fixtures/basic_project/pipelines/pl__orders")
        ),
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )


def build_raw_orders_row() -> tuple[object, ...]:
    return (
        "order-1-key",
        json.dumps(
            {
                "order_id": "order-1",
                "customer_id": "customer-7",
                "order_total": 42.5,
                "created_at": "2099-04-05 12:00:00.123",
                "updated_at": "2099-04-05 12:01:00.456",
            }
        ),
        "source.orders.created",
        0,
        1,
        "2099-04-05 12:00:00.123",
        0,
        1,
        "2099-04-05 12:00:00.123",
        ["trace-id"],
        ["order-1-trace"],
        "2099-04-05 12:00:00.789",
        "2099-04-05 12:00:00.789",
    )


def integer_rows(rows: Sequence[Sequence[object]]) -> tuple[tuple[int, ...], ...]:
    converted_rows: list[tuple[int, ...]] = []
    row: Sequence[object]
    for row in rows:
        converted_rows.append(tuple(int(str(value)) for value in row))
    return tuple(converted_rows)


def object_rows(rows: Sequence[Sequence[object]]) -> tuple[tuple[object, ...], ...]:
    converted_rows: list[tuple[object, ...]] = []
    row: Sequence[object]
    for row in rows:
        converted_rows.append(tuple(row))
    return tuple(converted_rows)


def build_invocation_record(
    *, invocation_id: str, project_identity: str, target_identity: str, completed_at: str
) -> AdapterInvocationRecord:
    return AdapterInvocationRecord(
        invocation_id=invocation_id,
        project_identity=project_identity,
        target_identity=target_identity,
        command="audit",
        mode=None,
        outcome="succeeded",
        exit_code=0,
        materialized_outcome=None,
        deployment_id=None,
        workflow_id=None,
        selected_node_count=1,
        started_at=completed_at,
        completed_at=completed_at,
        duration_ms=0,
        error_message=None,
        summary_json="{}",
        tool_version="1.2.3",
    )


def execute_rendered_statements(*, client: Client, statements: tuple[str, ...]) -> None:
    statement: str
    for statement in statements:
        _ = client.command(statement)


def run_metadata_migration(
    *,
    connection_settings: ClickHouseConnectionSettings,
    database: str,
    start_barrier: Barrier,
) -> None:
    connection: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=connection_settings.host,
            port=connection_settings.port,
            username=connection_settings.username,
            password=connection_settings.password,
            database=database,
        )
    )
    raw_client: Client = clickhouse_connect.get_client(
        host=connection_settings.host,
        port=connection_settings.port,
        username=connection_settings.username,
        password=connection_settings.password,
    )
    _ = start_barrier.wait()
    try:
        execute_rendered_statements(
            client=raw_client,
            statements=connection.render_migrate_metadata_state(database),
        )
    finally:
        connection.close()
        raw_client.close()


def connect_clickhouse(
    *, connection_settings: ClickHouseConnectionSettings, database: str
) -> AdapterConnection:
    return ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=connection_settings.host,
            port=connection_settings.port,
            username=connection_settings.username,
            password=connection_settings.password,
            database=database,
        )
    )
