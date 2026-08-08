import subprocess
import time
from pathlib import Path
from typing import cast

import pytest
from clickhouse_connect.driver.client import Client

from tests.e2e.src.streambuild.conftest import E2EClickHouseConnectionSettings
from tests.e2e.src.streambuild.dev_server._test_types import SchedulerProcessE2ETestCase
from tests.e2e.src.streambuild.dev_server.helpers import (
    available_port,
    read_json_url,
    start_dev_process,
    stop_process,
    wait_for_scheduled_result,
    wait_for_scheduler_api,
)
from tests.integration.src.streambuild.cli.helpers import (
    KEYED_ORDER_ITEMS_COLUMNS,
    KEYED_ORDER_ITEMS_ORDER_BY,
    build_order_items_ddl,
)
from tests.integration.src.streambuild.dev_server.helpers import write_scheduled_audit_project


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        SchedulerProcessE2ETestCase(
            description="dev lifecycle automatically runs audit and exposes scheduler APIs",
            expected_scheduler_state="idle",
            expected_result_status="warning",
            expected_run_mode="scheduled",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scheduler_enabled_dev_process_when_started_then_automatic_run_is_observable(
    test_case: SchedulerProcessE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    _ = write_scheduled_audit_project(
        project_dir=tmp_path,
        database=isolated_e2e_clickhouse_database,
        audit_query=(
            'SELECT order_id, line_total FROM __ref("order_items") '
            "WHERE sleep(2) = 0 AND line_total < 0"
        ),
    )
    isolated_e2e_clickhouse_client.command(
        build_order_items_ddl(
            database=isolated_e2e_clickhouse_database,
            columns=KEYED_ORDER_ITEMS_COLUMNS,
            order_by=KEYED_ORDER_ITEMS_ORDER_BY,
        )
    )
    isolated_e2e_clickhouse_client.insert(
        table=f"{isolated_e2e_clickhouse_database}.tbl__order_items",
        data=[["ord_001", -5.0]],
        column_names=["order_id", "line_total"],
    )
    api_port: int = available_port()
    second_api_port: int = available_port()
    repository_root: Path = Path(__file__).resolve().parents[5]
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=repository_root,
        project_dir=tmp_path,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        api_port=api_port,
    )
    second_process: subprocess.Popen[str] = start_dev_process(
        repository_root=repository_root,
        project_dir=tmp_path,
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
        database=isolated_e2e_clickhouse_database,
        api_port=second_api_port,
    )

    try:
        _ = wait_for_scheduler_api(process=process, api_port=api_port)
        _ = wait_for_scheduler_api(process=second_process, api_port=second_api_port)
        wait_for_scheduled_result(
            processes=(process, second_process),
            client=isolated_e2e_clickhouse_client,
            database=isolated_e2e_clickhouse_database,
        )
        time.sleep(0.2)
        scheduler_payloads: tuple[dict[str, object], dict[str, object]] = (
            wait_for_scheduler_api(process=process, api_port=api_port),
            wait_for_scheduler_api(process=second_process, api_port=second_api_port),
        )
        runs_payload: list[dict[str, object]] = cast(
            list[dict[str, object]],
            read_json_url(f"http://127.0.0.1:{api_port}/api/runs"),
        )
        checks_payload: list[dict[str, object]] = cast(
            list[dict[str, object]],
            read_json_url(f"http://127.0.0.1:{api_port}/api/checks/status"),
        )
    finally:
        stop_process(process)
        stop_process(second_process)

    result_count: int = int(
        isolated_e2e_clickhouse_client.query(
            f"SELECT count() FROM {isolated_e2e_clickhouse_database}."
            "_streambuild_node_results WHERE trigger = 'scheduled'"
        ).result_rows[0][0]
    )
    claim_count: int = int(
        isolated_e2e_clickhouse_client.query(
            f"SELECT count() FROM {isolated_e2e_clickhouse_database}."
            "_streambuild_audit_schedule_claims"
        ).result_rows[0][0]
    )
    scheduler_health_states: set[object] = {
        cast(dict[str, object], payload["health"])["state"] for payload in scheduler_payloads
    }
    scheduler_states: set[object] = {payload["state"] for payload in scheduler_payloads}

    assert process.poll() is not None
    assert second_process.poll() is not None
    assert "blocked" in scheduler_health_states
    assert test_case.expected_scheduler_state in scheduler_states
    assert runs_payload[0]["mode"] == test_case.expected_run_mode
    assert checks_payload[0]["status"] == test_case.expected_result_status
    assert result_count == 1
    assert claim_count == 2
