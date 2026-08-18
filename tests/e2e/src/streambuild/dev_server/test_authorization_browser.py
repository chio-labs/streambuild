from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import AuthorizationBrowserE2ETestCase
from tests.e2e.src.streambuild.dev_server.helpers import browser_post_reload


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        AuthorizationBrowserE2ETestCase(
            description="compiled project roles govern reload across every persona",
            expected_denied_status=403,
            expected_denied_reason="no_matching_assignment",
            expected_stale_reason="stale_assignment",
            expected_allowed_state="ok",
            expected_assigned_role="reload_operator",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_roles_when_operating_in_browser_then_effective_access_is_enforced(
    test_case: AuthorizationBrowserE2ETestCase,
    running_authorization_browser_server: tuple[str, Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _log_path, clickhouse_client, database = running_authorization_browser_server
    _console_messages, page_errors, _failed_requests, _responses = browser_diagnostics

    # Unassigned viewer: full read visibility, disabled control, denied mutation.
    page.set_extra_http_headers({"X-Mustard-User": "bob"})
    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    reload_button: Locator = page.get_by_role("button", name="Reload definitions", exact=True)
    expect(reload_button).to_be_visible()
    expect(reload_button).to_be_disabled()
    bob_reload: dict[str, object] = browser_post_reload(page=page)
    assert bob_reload["status"] == test_case.expected_denied_status
    assert bob_reload["reason"] == test_case.expected_denied_reason
    assert bob_reload["permission"] == "project.reload"

    # Assignment to a role removed from access.yml is stale and non-authorizing.
    page.set_extra_http_headers({"X-Mustard-User": "carol"})
    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    carol_reload: dict[str, object] = browser_post_reload(page=page)
    assert carol_reload["status"] == test_case.expected_denied_status
    assert carol_reload["reason"] == test_case.expected_stale_reason

    # An assignment pinned to another target does not authorize this target.
    page.set_extra_http_headers({"X-Mustard-User": "dave"})
    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    dave_reload: dict[str, object] = browser_post_reload(page=page)
    assert dave_reload["status"] == test_case.expected_denied_status
    assert dave_reload["reason"] == test_case.expected_denied_reason

    # Assigned operator: enabled control and successful reload from the UI.
    page.set_extra_http_headers({"X-Mustard-User": "alice"})
    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    alice_button: Locator = page.get_by_role("button", name="Reload definitions", exact=True)
    expect(alice_button).to_be_enabled()
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/reload"
    ) as reload_info:
        alice_button.click()
    assert reload_info.value.status == 200
    reload_payload: dict[str, object] = reload_info.value.json()
    compile_payload: dict[str, object] = reload_payload["compile"]  # type: ignore[assignment]
    assert compile_payload["state"] == test_case.expected_allowed_state

    # System administrator assigns the compiled role to Bob through the UI.
    page.set_extra_http_headers({"X-Mustard-User": "kevin"})
    assert page.goto(f"{base_url}/admin/users", wait_until="networkidle") is not None
    expect(page.get_by_text("Compiled roles", exact=True)).to_be_visible()
    expect(page.get_by_text(test_case.expected_assigned_role).first).to_be_visible()
    page.get_by_role("button", name="bob", exact=True).click()
    expect(page.get_by_text("No project roles assigned to bob.", exact=True)).to_be_visible()
    page.get_by_label("Project role name", exact=True).select_option(
        label=test_case.expected_assigned_role
    )
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/project-roles")
            and response.request.method == "POST"
        )
    ) as grant_info:
        page.get_by_role("button", name="assign role", exact=True).click()
    assert grant_info.value.status == 200
    assert grant_info.value.json()["role"] == test_case.expected_assigned_role
    assignment_row: Locator = page.get_by_role("row").filter(has_text="all targets")
    expect(assignment_row).to_contain_text(test_case.expected_assigned_role)
    expect(assignment_row).to_contain_text("active")

    # The assignment takes effect on Bob's next request without a server restart.
    page.set_extra_http_headers({"X-Mustard-User": "bob"})
    assert page.goto(f"{base_url}/status", wait_until="networkidle") is not None
    expect(page.get_by_role("button", name="Reload definitions", exact=True)).to_be_enabled()
    bob_allowed: dict[str, object] = browser_post_reload(page=page)
    assert bob_allowed["status"] == 200

    # A non-admin pipeline grant crosses the real authorization boundary and
    # executes the real child-process build against ClickHouse.
    page.set_extra_http_headers({"X-Mustard-User": "alice"})
    assert page.goto(f"{base_url}/plan?select=moving_orders", wait_until="networkidle") is not None
    execute: Locator = page.get_by_role("button", name="Execute", exact=True)
    expect(execute).to_be_enabled(timeout=30_000)
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/build" and response.request.method == "POST"
        )
    ) as build_info:
        execute.click()
    assert build_info.value.status == 200
    expect(page.get_by_text("succeeded", exact=True).first).to_be_visible(timeout=120_000)
    built_rows: list[Sequence[object]] = list(
        clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__moving_orders ORDER BY order_id"
        ).result_rows
    )
    assert built_rows == [("authorized-build",)]

    assert page_errors == []


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
