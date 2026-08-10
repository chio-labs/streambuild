from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import (
    APIResponse,
    ConsoleMessage,
    Error,
    Locator,
    Page,
    Request,
    Response,
    expect,
)

from tests.e2e.src.streambuild.dev_server._test_types import QualityBrowserE2ETestCase


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        QualityBrowserE2ETestCase(
            description="scheduled pass warning and failure remain persisted and distinct",
            expected_passing=1,
            expected_warning=1,
            expected_failing=1,
            expected_sample_key="ord_001",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_scheduled_audits_when_filtering_quality_then_outcomes_remain_exact(
    test_case: QualityBrowserE2ETestCase,
    running_quality_browser_server: tuple[str, str, tuple[str, str, str], Path],
    e2e_clickhouse_client: Client,
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, database, audit_names, _log_path = running_quality_browser_server
    passing_name, warning_name, failing_name = audit_names
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    persisted_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT node_name, status, severity, failure_count, trigger, "
            f"isNotNull(scheduled_for) FROM {database}._streambuild_node_results "
            "WHERE trigger = 'scheduled' ORDER BY node_name"
        ).result_rows
    )
    assert len(persisted_rows) == 3
    status_by_name: dict[str, tuple[object, ...]] = {str(row[0]): row[1:] for row in persisted_rows}
    assert status_by_name[passing_name] == ("passed", "error", 0, "scheduled", 1)
    assert status_by_name[warning_name] == ("warning", "warning", 1, "scheduled", 1)
    assert status_by_name[failing_name] == ("failed", "error", 1, "scheduled", 1)

    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/checks/status"
    ) as checks_info:
        document_response: Response | None = page.goto(
            f"{base_url}/quality", wait_until="domcontentloaded", timeout=30_000
        )
    assert document_response is not None
    assert document_response.status == 200
    checks_payload: list[dict[str, object]] = checks_info.value.json()
    check_by_name: dict[str, dict[str, object]] = {
        str(check["name"]): check for check in checks_payload
    }
    assert check_by_name[passing_name]["status"] == "passed"
    assert check_by_name[warning_name]["status"] == "warning"
    assert check_by_name[failing_name]["status"] == "failed"
    expect(page.get_by_text(f"audits {test_case.expected_passing}/3", exact=False)).to_be_visible()
    expect(page.get_by_text(f"{test_case.expected_warning} warn", exact=True)).to_be_visible()
    expect(page.get_by_text(f"{test_case.expected_failing} fail", exact=True)).to_be_visible()

    passing_row: Locator = page.locator(f'[data-quality-name="{passing_name}"]')
    warning_row: Locator = page.locator(f'[data-quality-name="{warning_name}"]')
    failing_row: Locator = page.locator(f'[data-quality-name="{failing_name}"]')
    expect(passing_row).to_contain_text("pass")
    expect(passing_row).to_contain_text("error")
    expect(warning_row).to_contain_text("warning")
    expect(warning_row).to_contain_text("1 rows")
    expect(failing_row).to_contain_text("error")
    expect(failing_row).to_contain_text("1 rows")

    warning_expand: Locator = page.get_by_role(
        "button", name=f"Expand audit {warning_name}", exact=True
    )
    warning_expand.click()
    expect(warning_expand).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_text("Violating rows — sample of 1", exact=True)).to_be_visible()
    expect(page.get_by_role("cell", name=test_case.expected_sample_key, exact=True)).to_be_visible()
    expect(page.get_by_role("cell", name="-5", exact=True)).to_be_visible()

    e2e_clickhouse_client.command(f"TRUNCATE TABLE {database}.tbl__order_items")
    e2e_clickhouse_client.insert(
        table=f"{database}.tbl__order_items",
        data=[[test_case.expected_sample_key, 5.0]],
        column_names=["order_id", "line_total"],
    )
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/checks/run" and response.request.method == "POST"
        )
    ) as manual_info:
        page.get_by_role("button", name="run audit", exact=True).click()
    manual_payload: dict[str, object] = manual_info.value.json()
    assert manual_payload["name"] == warning_name
    assert manual_payload["passed"] is True
    expect(warning_row).to_contain_text("pass")
    expect(page.get_by_text("audits 2/3", exact=False)).to_be_visible()
    expect(page.get_by_text("1 warn", exact=True)).to_have_count(0)

    page.get_by_role("button", name="Failing", exact=True).click()
    expect(page.get_by_role("button", name="Failing", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(passing_row).to_have_count(0)
    expect(warning_row).to_have_count(0)
    expect(failing_row).to_be_visible()
    page.get_by_role("button", name="Passing", exact=True).click()
    expect(passing_row).to_be_visible()
    expect(warning_row).to_be_visible()
    expect(failing_row).to_have_count(0)

    page.get_by_role("button", name="All", exact=True).click()
    with page.expect_response(lambda response: urlparse(response.url).path == "/api/checks/status"):
        page.get_by_role("button", name="Refresh snapshot", exact=True).click()
    for audit_name in audit_names:
        expect(page.locator(f'[data-quality-name="{audit_name}"]')).to_have_count(1)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_text("audits 2/3", exact=False)).to_be_visible()
    for audit_name in audit_names:
        expect(page.locator(f'[data-quality-name="{audit_name}"]')).to_have_count(1)

    scheduler_response: APIResponse = page.request.get(f"{base_url}/api/audit-scheduler")
    assert scheduler_response.status == 200
    scheduler_payload: dict[str, object] = scheduler_response.json()
    scheduler_health: dict[str, object] = cast(dict[str, object], scheduler_payload["health"])
    assert scheduler_health["state"] == "idle"
    runs_response: APIResponse = page.request.get(f"{base_url}/api/runs")
    assert runs_response.status == 200
    runs_payload: list[dict[str, object]] = runs_response.json()
    run_by_mode: dict[str, dict[str, object]] = {str(run["mode"]): run for run in runs_payload}
    assert run_by_mode["scheduled"]["outcome"] == "failed"
    assert run_by_mode["None"]["outcome"] == "succeeded"
    scheduled_count: int = int(
        e2e_clickhouse_client.query(
            f"SELECT count() FROM {database}._streambuild_node_results WHERE trigger = 'scheduled'"
        ).result_rows[0][0]
    )
    assert scheduled_count == 3
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)
