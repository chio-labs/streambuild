import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient
from playwright.sync_api import ConsoleMessage, Error, Page, Request, Response

from streambuild.compiler.compile.models import CompiledPipeline
from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.dev_server.helpers import (
    available_port,
    create_lineage_browser_source_tables,
    prepare_lineage_browser_project,
    run_lineage_browser_build,
    seed_lineage_approximate_activity,
    seed_lineage_plan_replay_data,
    start_dev_process,
    stop_process,
    wait_for_scheduler_api,
    wait_for_state_api,
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
from tests.integration.src.streambuild.executor.backfill._test_types import ManagedSourceResources


@pytest.fixture
def running_lineage_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, dict[str, object], Path, Client, str]]:
    repository_root: Path = Path(__file__).resolve().parents[5]
    project_dir: Path = prepare_lineage_browser_project(tmp_path=tmp_path)
    create_lineage_browser_source_tables(
        client=e2e_clickhouse_client, database=e2e_clickhouse_database
    )
    run_lineage_browser_build(
        repository_root=repository_root,
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=repository_root,
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
        state_payload: dict[str, object] = wait_for_state_api(
            process=process, api_port=api_port, log_path=log_path
        )
        yield (
            f"http://127.0.0.1:{api_port}",
            state_payload,
            log_path,
            e2e_clickhouse_client,
            e2e_clickhouse_database,
        )
    finally:
        stop_process(process)


@pytest.fixture
def running_plan_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, dict[str, object], Path, Client, str]]:
    repository_root: Path = Path(__file__).resolve().parents[5]
    project_dir: Path = prepare_lineage_browser_project(tmp_path=tmp_path)
    create_lineage_browser_source_tables(
        client=e2e_clickhouse_client, database=e2e_clickhouse_database
    )
    run_lineage_browser_build(
        repository_root=repository_root,
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
    )
    seed_lineage_plan_replay_data(client=e2e_clickhouse_client, database=e2e_clickhouse_database)
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-plan.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=repository_root,
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
        state_payload: dict[str, object] = wait_for_state_api(
            process=process, api_port=api_port, log_path=log_path
        )
        yield (
            f"http://127.0.0.1:{api_port}",
            state_payload,
            log_path,
            e2e_clickhouse_client,
            e2e_clickhouse_database,
        )
    finally:
        stop_process(process)


@pytest.fixture
def running_message_browser_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, str, str, str, Path]]:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    managed_source: ManagedSourceResources = require_managed_source(compiled_pipeline)
    topic: str = managed_source.kafka_table.spec.kafka.topic
    unmanaged_topic: str = f"unmanaged-{e2e_clickhouse_database}"
    kafka_table_ddl: str = render_create_kafka_table_ddl(
        table=managed_source.kafka_table, database=e2e_clickhouse_database
    )
    assert e2e_kafka_connection_settings.bootstrap_server in kafka_table_ddl
    e2e_clickhouse_client.command(
        kafka_table_ddl.replace(
            e2e_kafka_connection_settings.bootstrap_server,
            e2e_kafka_connection_settings.internal_bootstrap_server,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(table=managed_source.raw_table, database=e2e_clickhouse_database)
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=managed_source.materialized_view,
            database=e2e_clickhouse_database,
        )
    )
    full_record_detail: str = f"browser-full-record-{'x' * 600}"
    messages: tuple[tuple[str, str], ...] = tuple(
        (
            f"order-{index:02d}",
            json.dumps(
                {
                    "order_id": f"order-{index:02d}",
                    "message_type": "created",
                    **({"detail": full_record_detail} if index == 2 else {}),
                },
                separators=(",", ":"),
            ),
        )
        for index in range(1, 13)
    )
    expected_full_value: str = messages[1][1]
    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=topic,
            messages=messages,
            headers=(("trace-id", b"browser"),),
        )
        produce_kafka_messages(
            producer=producer,
            topic=unmanaged_topic,
            messages=(("unmanaged", '{"kind":"inventory"}'),),
        )
    finally:
        producer.close()
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=managed_source.raw_table.name,
        expected_count=len(messages),
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-message-browser.log"
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
        yield (
            f"http://127.0.0.1:{api_port}",
            topic,
            unmanaged_topic,
            expected_full_value,
            log_path,
        )
    finally:
        stop_process(process)
        admin_client: KafkaAdminClient = KafkaAdminClient(
            bootstrap_servers=e2e_kafka_connection_settings.bootstrap_server
        )
        try:
            admin_client.delete_topics(topics=[topic, unmanaged_topic])
        finally:
            admin_client.close()


@pytest.fixture
def running_no_activity_log_lineage_server(
    no_activity_log_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    no_activity_log_clickhouse_client: Client,
    no_activity_log_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, dict[str, object], Path]]:
    repository_root: Path = Path(__file__).resolve().parents[5]
    project_dir: Path = prepare_lineage_browser_project(tmp_path=tmp_path)
    capabilities: tuple[Sequence[object], ...] = tuple(
        no_activity_log_clickhouse_client.query(
            "SELECT name FROM system.tables WHERE database = 'system' "
            "AND name IN ('part_log', 'query_views_log') ORDER BY name"
        ).result_rows
    )
    assert capabilities == ()
    create_lineage_browser_source_tables(
        client=no_activity_log_clickhouse_client,
        database=no_activity_log_clickhouse_database,
    )
    run_lineage_browser_build(
        repository_root=repository_root,
        project_dir=project_dir,
        host=no_activity_log_clickhouse_connection_settings.host,
        port=no_activity_log_clickhouse_connection_settings.port,
        username=no_activity_log_clickhouse_connection_settings.username,
        password=no_activity_log_clickhouse_connection_settings.password,
        database=no_activity_log_clickhouse_database,
    )
    seed_lineage_approximate_activity(
        client=no_activity_log_clickhouse_client,
        database=no_activity_log_clickhouse_database,
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-no-activity-logs.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=repository_root,
        project_dir=project_dir,
        host=no_activity_log_clickhouse_connection_settings.host,
        port=no_activity_log_clickhouse_connection_settings.port,
        username=no_activity_log_clickhouse_connection_settings.username,
        password=no_activity_log_clickhouse_connection_settings.password,
        database=no_activity_log_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        state_payload: dict[str, object] = wait_for_state_api(
            process=process, api_port=api_port, log_path=log_path
        )
        yield f"http://127.0.0.1:{api_port}", state_payload, log_path
    finally:
        stop_process(process)


@pytest.fixture
def browser_diagnostics(
    output_path: str,
    page: Page,
) -> Iterator[tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]]]:
    console_messages: list[ConsoleMessage] = []
    page_errors: list[Error] = []
    failed_requests: list[Request] = []
    responses: list[Response] = []
    page.on("console", lambda message: console_messages.append(message))
    page.on("pageerror", lambda error: page_errors.append(error))
    page.on("requestfailed", lambda request: failed_requests.append(request))
    page.on("response", lambda response: responses.append(response))
    try:
        yield console_messages, page_errors, failed_requests, responses
    finally:
        artifacts_path: Path = Path(output_path)
        artifacts_path.mkdir(parents=True, exist_ok=True)
        (artifacts_path / "browser-diagnostics.txt").write_text(
            "--- console ---\n"
            + "\n".join(f"{message.type}: {message.text}" for message in console_messages)
            + "\n--- page errors ---\n"
            + "\n".join(str(error) for error in page_errors)
            + "\n--- failed requests ---\n"
            + "\n".join(
                f"{request.method} {request.url} {request.failure}" for request in failed_requests
            )
            + "\n--- responses ---\n"
            + "\n".join(f"{response.status} {response.url}" for response in responses)
            + "\n",
            encoding="utf-8",
        )
