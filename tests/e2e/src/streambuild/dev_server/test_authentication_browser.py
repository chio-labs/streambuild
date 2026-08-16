import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import ConsoleMessage, Error, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import (
    PasswordAuthenticationBrowserE2ETestCase,
)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        PasswordAuthenticationBrowserE2ETestCase(
            description="password session logs in, expires, redirects, and logs out",
            username="alice",
            password="correct horse battery staple",
            expected_session_ttl_seconds=5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_password_mode_when_session_changes_then_browser_follows_full_lifecycle(
    test_case: PasswordAuthenticationBrowserE2ETestCase,
    running_password_browser_server: tuple[str, Path, int],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _log_path, session_ttl_seconds = running_password_browser_server
    _console_messages, page_errors, failed_requests, _responses = browser_diagnostics
    assert session_ttl_seconds == test_case.expected_session_ttl_seconds

    page.goto(f"{base_url}/status", wait_until="domcontentloaded")
    expect(page).to_have_url(re.compile(r"/login$"))
    page.get_by_label("Username").fill(test_case.username)
    page.get_by_label("Password").fill(test_case.password)
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/auth/login"
    ) as login_info:
        page.get_by_role("button", name="sign in", exact=True).click()
    assert login_info.value.status == 200
    expect(page).to_have_url(re.compile(r"/$"), timeout=30_000)
    expect(page.get_by_text(test_case.username, exact=True)).to_be_visible()

    page.wait_for_timeout((session_ttl_seconds + 1) * 1000)
    page.goto(f"{base_url}/status", wait_until="domcontentloaded")
    expect(page).to_have_url(re.compile(r"/login$"))

    page.get_by_label("Username").fill(test_case.username)
    page.get_by_label("Password").fill(test_case.password)
    page.get_by_role("button", name="sign in", exact=True).click()
    expect(page).to_have_url(re.compile(r"/$"), timeout=30_000)
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/auth/logout"
    ) as logout_info:
        page.get_by_role("button", name="Sign out", exact=True).click()
    assert logout_info.value.status == 200
    expect(page).to_have_url(re.compile(r"/login$"))
    assert page_errors == []
    assert failed_requests == []
