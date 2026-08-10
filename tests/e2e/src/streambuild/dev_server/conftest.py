import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import ConsoleMessage, Error, Page, Request, Response

from tests.e2e.src.streambuild.conftest import E2EClickHouseConnectionSettings
from tests.e2e.src.streambuild.dev_server.helpers import (
    available_port,
    create_lineage_browser_source_tables,
    prepare_lineage_browser_project,
    run_lineage_browser_build,
    seed_lineage_approximate_activity,
    start_dev_process,
    stop_process,
    wait_for_state_api,
)


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
