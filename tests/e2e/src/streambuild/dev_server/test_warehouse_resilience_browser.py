from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import (
    APIResponse,
    ConsoleMessage,
    Error,
    Locator,
    Page,
    Request,
    Response,
    Route,
    expect,
)

from tests.e2e.src.streambuild.dev_server._test_types import DevServerBrowserE2ETestCase


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        DevServerBrowserE2ETestCase(
            description="warehouse outage keeps definitions and recovery controls available",
            expected_connected=False,
            expected_compile_state="ok",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unreachable_warehouse_when_using_ui_then_snapshot_and_definitions_remain_operable(
    test_case: DevServerBrowserE2ETestCase,
    running_disconnected_browser_server: tuple[str, Path, Path],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, project_dir, _log_path = running_disconnected_browser_server
    _console_messages, page_errors, failed_requests, _responses = browser_diagnostics

    def clear_pending_connection_error(route: Route) -> None:
        response: APIResponse = route.fetch()
        payload: dict[str, object] = response.json()
        warehouse: object | None = payload.get("warehouse")
        assert isinstance(warehouse, dict)
        warehouse["error"] = None
        route.fulfill(response=response, json=payload)

    page.route("**/api/status", clear_pending_connection_error)

    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    expect(page.get_by_text("Warehouse unavailable.", exact=True)).to_be_visible()
    expect(
        page.get_by_text(
            "Live ingest, freshness, catalog, deployment, and quality state cannot be read.",
            exact=False,
        )
    ).to_be_visible()
    expect(page.get_by_text("Project compile", exact=True)).to_be_visible()
    refresh: Locator = page.get_by_role("button", name="Refresh snapshot", exact=True)
    reload_definitions: Locator = page.get_by_role("button", name="Reload definitions", exact=True)
    expect(refresh).to_be_enabled()
    expect(reload_definitions).to_be_enabled()

    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/warehouse/refresh"
    ) as refresh_info:
        refresh.click()
    assert refresh_info.value.status == 200
    assert refresh_info.value.json()["warehouse"]["connected"] is test_case.expected_connected

    model_path: Path = project_dir / "pipelines" / "pl__moving_events" / "moving_orders.sql"
    model_path.write_text(model_path.read_text(encoding="utf-8") + "\n-- browser reload\n")
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/reload"
    ) as reload_info:
        reload_definitions.click()
    assert reload_info.value.status == 200
    assert reload_info.value.json()["compile"]["state"] == test_case.expected_compile_state
    expect(page.get_by_text("Warehouse unavailable.", exact=True)).to_be_visible()

    page.get_by_role("link", name="Warehouse", exact=True).click()
    expect(page).to_have_url(f"{base_url}/warehouse-health")
    expect(page.get_by_test_id("warehouse-health-page")).to_be_visible()
    expect(page.get_by_text("Diagnostics unavailable", exact=True)).to_be_visible()
    expect(page.get_by_text("HEALTHY", exact=True)).to_have_count(0)
    assert page_errors == []
    assert failed_requests == []


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
