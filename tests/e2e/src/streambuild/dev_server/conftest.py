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
    prepare_catalog_pipeline_browser_project,
    prepare_lineage_browser_project,
    run_lineage_browser_build,
    seed_lineage_approximate_activity,
    seed_lineage_plan_replay_data,
    start_dev_process,
    stop_process,
    wait_for_scheduled_result,
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
    run_streambuild_build_cli,
    run_streambuild_deployment_promote_cli,
    run_streambuild_virtual_build_cli,
    wait_for_row_count,
)
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    render_create_kafka_table_ddl,
    render_create_materialized_view_ddl,
    render_create_table_ddl,
)
from tests.integration.src.streambuild.cli.helpers import (
    KEYED_ORDER_ITEMS_COLUMNS,
    KEYED_ORDER_ITEMS_ORDER_BY,
    build_order_items_ddl,
    prepare_virtual_environment_view_sources,
    write_virtual_environment_view_model,
    write_virtual_environment_view_project,
)
from tests.integration.src.streambuild.dev_server.helpers import write_scheduled_audit_project
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
    (project_dir / "pipelines" / "pl__moving_events" / "pipeline.toml").write_text(
        'mode = "direct"\n\n'
        "[protection]\n"
        'warning = "Interrupts protected moving events."\n'
        'confirmation = "DEPLOY_MOVING_EVENTS"\n',
        encoding="utf-8",
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
def running_catalog_pipeline_browser_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, dict[str, object], str, Path]]:
    repository_root: Path = Path(__file__).resolve().parents[5]
    project_dir: Path = prepare_catalog_pipeline_browser_project(tmp_path=tmp_path)
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
    e2e_clickhouse_client.command(
        f"INSERT INTO {e2e_clickhouse_database}.browser_moving_events "
        "(order_id, event_timestamp) VALUES ('catalog-42', now64(3))"
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-catalog-pipeline.log"
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
            e2e_clickhouse_database,
            log_path,
        )
    finally:
        stop_process(process)


@pytest.fixture
def running_deployment_browser_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, str, str, str, Path]]:
    active_deployment_id: str = "20260810T120000Z_before"
    staged_deployment_id: str = "20260810T121000Z_after"
    write_virtual_environment_view_project(project_root=tmp_path)
    prepare_virtual_environment_view_sources(
        clickhouse_client=e2e_clickhouse_client, database=e2e_clickhouse_database
    )
    connection: E2EClickHouseConnectionSettings = e2e_clickhouse_connection_settings
    run_streambuild_virtual_build_cli(
        project_dir=tmp_path,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        deployment_id=active_deployment_id,
    )
    run_streambuild_deployment_promote_cli(
        project_dir=tmp_path,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        deployment_id=active_deployment_id,
    )
    write_virtual_environment_view_model(
        project_root=tmp_path,
        customer_name_expression="CAST(concat(customers.customer_name, '!') AS String)",
    )
    run_streambuild_virtual_build_cli(
        project_dir=tmp_path,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        deployment_id=staged_deployment_id,
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-deployments.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=Path(__file__).resolve().parents[5],
        project_dir=tmp_path,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        _ = wait_for_state_api(process=process, api_port=api_port, log_path=log_path)
        yield (
            f"http://127.0.0.1:{api_port}",
            active_deployment_id,
            staged_deployment_id,
            e2e_clickhouse_database,
            log_path,
        )
    finally:
        stop_process(process)


@pytest.fixture
def running_quality_browser_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, str, tuple[str, str, str], Path]]:
    passing_name: str = "scheduled valid line totals"
    warning_name: str = "scheduled negative line totals"
    failing_name: str = "scheduled hard negative line totals"
    _ = write_scheduled_audit_project(
        project_dir=tmp_path,
        database=e2e_clickhouse_database,
        severity="warning",
        audit_query=('SELECT order_id, line_total FROM __ref("order_items") WHERE line_total < 0'),
    )
    audits_dir: Path = tmp_path / "audits" / "singular" / "order_events"
    (audits_dir / "valid_line_totals.sql").write_text(
        f'AUDIT (name "{passing_name}", severity error);\n\n'
        'SELECT order_id, line_total FROM __ref("order_items") WHERE line_total < -100\n',
        encoding="utf-8",
    )
    (audits_dir / "hard_negative_line_totals.sql").write_text(
        f'AUDIT (name "{failing_name}", severity error);\n\n'
        'SELECT order_id, line_total FROM __ref("order_items") WHERE line_total < 0\n',
        encoding="utf-8",
    )
    e2e_clickhouse_client.command(
        build_order_items_ddl(
            database=e2e_clickhouse_database,
            columns=KEYED_ORDER_ITEMS_COLUMNS,
            order_by=KEYED_ORDER_ITEMS_ORDER_BY,
        )
    )
    e2e_clickhouse_client.insert(
        table=f"{e2e_clickhouse_database}.tbl__order_items",
        data=[["ord_001", -5.0]],
        column_names=["order_id", "line_total"],
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-quality.log"
    connection: E2EClickHouseConnectionSettings = e2e_clickhouse_connection_settings
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=Path(__file__).resolve().parents[5],
        project_dir=tmp_path,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        _ = wait_for_scheduler_api(process=process, api_port=api_port, log_path=log_path)
        wait_for_scheduled_result(
            processes=(process,),
            client=e2e_clickhouse_client,
            database=e2e_clickhouse_database,
            expected_count=3,
        )
        yield (
            f"http://127.0.0.1:{api_port}",
            e2e_clickhouse_database,
            (passing_name, warning_name, failing_name),
            log_path,
        )
    finally:
        stop_process(process)


@pytest.fixture
def running_complete_streaming_browser_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, str, str, Path]]:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    (project_dir / "streambuild_project.toml").write_text(
        'name = "e2e_kafka_lineage_browser_project"\n'
        'default_target = "test"\n\n'
        '[defaults]\npipeline_mode = "direct"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    (project_dir / "pipelines" / "pl__order_events" / "orders_enriched.sql").write_text(
        'MODEL (\n  engine "MergeTree()",\n'
        '  order_by ["order_id", "_replay_timestamp"]\n);\n\n'
        "SELECT\n  CAST(concat('enriched:', order_id) AS String) AS order_id,\n"
        "  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp,\n"
        "  CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at\n"
        'FROM __ref("orders")\n',
        encoding="utf-8",
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    topic: str = require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic
    connection: E2EClickHouseConnectionSettings = e2e_clickhouse_connection_settings
    run_streambuild_build_cli(
        project_dir=project_dir,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev-complete-streaming.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=Path(__file__).resolve().parents[5],
        project_dir=project_dir,
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=e2e_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        _ = wait_for_state_api(process=process, api_port=api_port, log_path=log_path)
        yield (
            f"http://127.0.0.1:{api_port}",
            topic,
            e2e_kafka_connection_settings.bootstrap_server,
            log_path,
        )
    finally:
        stop_process(process)
        admin_client: KafkaAdminClient = KafkaAdminClient(
            bootstrap_servers=e2e_kafka_connection_settings.bootstrap_server
        )
        try:
            admin_client.delete_topics(topics=[topic])
        finally:
            admin_client.close()


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
