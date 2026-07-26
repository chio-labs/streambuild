import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer

from streambuild.clickhouse.render._helpers.create_kafka_table import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render._helpers.create_materialized_view import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table import render_create_table_ddl
from streambuild.compiler.compile.models import CompiledPipeline
from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.executor._test_types import KafkaLiveShadowWorkflowE2ETestCase
from tests.e2e.src.streambuild.executor.helpers import (
    E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
    build_authored_greenfield_workflow_compiled_pipeline,
    build_kafka_producer,
    prepare_authored_e2e_project,
    produce_kafka_messages,
    require_managed_source,
    run_streambuild_backfill_cli,
    run_streambuild_publish_cli,
    wait_for_live_shadow_row_count,
    wait_for_row_count,
)


@dataclass(frozen=True)
class KafkaLiveShadowScenarioResult:
    staged_table_name: str
    staged_order_ids: tuple[str, ...]
    deployment_id: str
    final_rows: tuple[tuple[object, ...], ...]


def run_kafka_live_shadow_scenario(
    *,
    test_case: KafkaLiveShadowWorkflowE2ETestCase,
    clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    kafka_connection_settings: E2EKafkaConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    tmp_path: Path,
) -> KafkaLiveShadowScenarioResult:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    target_table_name: str = compiled_pipeline.transforms[0].target_table_name
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

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.initial_order_ids
            ),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.initial_order_ids),
    )
    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
        database=clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    staged_table_name: str = f"{target_table_name}__{test_case.deployment_id}"
    wait_for_live_shadow_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        raw_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        staged_table_name=staged_table_name,
        expected_count=len(test_case.initial_order_ids),
    )

    producer = build_kafka_producer(bootstrap_server=kafka_connection_settings.bootstrap_server)
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.live_order_ids
            ),
        )
    finally:
        producer.close()

    total_order_count: int = len(test_case.initial_order_ids) + len(test_case.live_order_ids)
    wait_for_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=total_order_count,
    )
    wait_for_live_shadow_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        raw_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        staged_table_name=staged_table_name,
        expected_count=total_order_count,
    )
    staged_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {clickhouse_database}.{staged_table_name} ORDER BY order_id"
    ).result_rows

    run_streambuild_publish_cli(
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
        database=clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    final_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {clickhouse_database}.{target_table_name} ORDER BY order_id"
    ).result_rows
    return KafkaLiveShadowScenarioResult(
        staged_table_name=staged_table_name,
        staged_order_ids=tuple(str(row[0]) for row in staged_rows),
        deployment_id=test_case.deployment_id,
        final_rows=tuple(tuple(row) for row in final_rows),
    )
