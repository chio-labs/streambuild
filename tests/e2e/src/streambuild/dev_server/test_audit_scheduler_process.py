import subprocess
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
    log_path: Path = tmp_path / "stb-dev-audit-scheduler.log"
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
        log_path=log_path,
    )
    try:
        _ = wait_for_scheduler_api(process=process, api_port=api_port, log_path=log_path)
        wait_for_scheduled_result(
            processes=(process,),
            client=isolated_e2e_clickhouse_client,
            database=isolated_e2e_clickhouse_database,
        )
        scheduler_payload: dict[str, object] = wait_for_scheduler_api(
            process=process, api_port=api_port, log_path=log_path
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

    result_count: int = int(
        isolated_e2e_clickhouse_client.query(
            f"SELECT count() FROM {isolated_e2e_clickhouse_database}."
            "_streambuild_node_results WHERE trigger = 'scheduled'"
        ).result_rows[0][0]
    )
    scheduler_health: dict[str, object] = cast(dict[str, object], scheduler_payload["health"])

    assert process.poll() is not None
    assert scheduler_health["state"] == test_case.expected_scheduler_state
    assert scheduler_payload["state"] == test_case.expected_scheduler_state
    assert runs_payload[0]["mode"] == test_case.expected_run_mode
    assert checks_payload[0]["status"] == test_case.expected_result_status
    assert result_count == 1
