import subprocess
from pathlib import Path
from typing import cast

import pytest
from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer

from streambuild.compiler.compile.models import CompiledPipeline
from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.dev_server._test_types import MessageBrowserProcessE2ETestCase
from tests.e2e.src.streambuild.dev_server.helpers import (
    available_port,
    post_json_url,
    read_json_url,
    start_dev_process,
    stop_process,
    wait_for_scheduler_api,
)
from tests.e2e.src.streambuild.executor.helpers import (
    E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
    build_authored_greenfield_workflow_compiled_pipeline,
    build_kafka_producer,
    prepare_authored_e2e_project,
    produce_kafka_messages,
    require_managed_source,
    wait_for_row_count,
)
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    render_create_kafka_table_ddl,
    render_create_materialized_view_ddl,
    render_create_table_ddl,
)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        MessageBrowserProcessE2ETestCase(
            description="dev process serves filtered messages, records, facets, and topics",
            produced_messages=(
                ("order-1", '{"order_id": "order-1"}', (("trace-id", b"one"),)),
                ("order-2", '{"order_id": "order-2"}', (("trace-id", b"two"),)),
                ("order-3", '{"order_id": "order-3"}', ()),
            ),
            filtered_order_id="order-2",
            expected_filtered_key="order-2",
            expected_filtered_headers=(("trace-id", "two"),),
            expected_facet_values=("order-1", "order-2", "order-3"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_landed_kafka_messages_when_browsing_through_dev_api_then_filters_serve_truthfully(
    test_case: MessageBrowserProcessE2ETestCase,
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    topic: str = require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic
    e2e_clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=e2e_clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        for message_key, message_value, headers in test_case.produced_messages:
            produce_kafka_messages(
                producer=producer,
                topic=topic,
                messages=((message_key, message_value),),
                headers=headers,
            )
    finally:
        producer.close()
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.produced_messages),
    )

    api_port: int = available_port()
    log_path: Path = tmp_path / "stb-dev-message-browser.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=Path(__file__).resolve().parents[5],
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        _ = wait_for_scheduler_api(process=process, api_port=api_port, log_path=log_path)
        filtered: dict[str, object] = cast(
            dict[str, object],
            post_json_url(
                f"http://127.0.0.1:{api_port}/api/sources/order_events/messages",
                {
                    "limit": 10,
                    "predicates": [
                        {
                            "field": "json",
                            "path": ["order_id"],
                            "op": "eq",
                            "value": test_case.filtered_order_id,
                        }
                    ],
                },
            ),
        )
        filtered_rows: list[dict[str, object]] = cast(list[dict[str, object]], filtered["rows"])
        record: dict[str, object] = cast(
            dict[str, object],
            post_json_url(
                f"http://127.0.0.1:{api_port}/api/sources/order_events/messages/record",
                {
                    "partition": filtered_rows[0]["partition"],
                    "offset": filtered_rows[0]["offset"],
                },
            ),
        )
        facets: dict[str, object] = cast(
            dict[str, object],
            post_json_url(
                f"http://127.0.0.1:{api_port}/api/sources/order_events/messages/facets",
                {"facetPath": ["order_id"]},
            ),
        )
        topics: dict[str, object] = cast(
            dict[str, object],
            read_json_url(f"http://127.0.0.1:{api_port}/api/topics"),
        )
    finally:
        stop_process(process)

    assert [row["key"] for row in filtered_rows] == [test_case.expected_filtered_key]
    assert filtered_rows[0]["headers"] == [
        list(pair) for pair in test_case.expected_filtered_headers
    ]
    assert record["value"] == f'{{"order_id": "{test_case.filtered_order_id}"}}'
    assert record["topic"] == topic
    facet_values: list[dict[str, object]] = cast(list[dict[str, object]], facets["values"])
    assert sorted(str(value["value"]) for value in facet_values) == sorted(
        test_case.expected_facet_values
    )
    assert facets["totalCount"] == len(test_case.produced_messages)
    assert topics["available"] is True
    topics_by_name: dict[str, dict[str, object]] = {
        str(item["name"]): item for item in cast(list[dict[str, object]], topics["topics"])
    }
    managed_topic: dict[str, object] = topics_by_name[topic]
    sources: list[dict[str, object]] = cast(list[dict[str, object]], managed_topic["sources"])
    assert [source["name"] for source in sources] == ["order_events"]
    assert managed_topic["retainedRows"] == len(test_case.produced_messages)
