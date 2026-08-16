from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import TrustedProxyBrowserE2ETestCase
from tests.e2e.src.streambuild.dev_server.helpers import browser_post_reload


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        TrustedProxyBrowserE2ETestCase(
            description="proxy replaces a spoofed identity before authorization",
            spoofed_username="kevin",
            expected_username="bob",
            expected_denied_reason="no_matching_assignment",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_spoofed_identity_when_proxying_then_proxy_replaces_header_before_authorization(
    test_case: TrustedProxyBrowserE2ETestCase,
    running_header_replacing_proxy: tuple[str, Path],
    page: Page,
) -> None:
    base_url, _log_path = running_header_replacing_proxy
    page.set_extra_http_headers({"X-Mustard-User": test_case.spoofed_username})

    response: Response | None = page.goto(f"{base_url}/status", wait_until="networkidle")

    assert response is not None
    assert response.status == 200
    expect(page.get_by_text(test_case.expected_username, exact=True)).to_be_visible()
    reload_button: Locator = page.get_by_role("button", name="reload", exact=True)
    expect(reload_button).to_be_disabled()
    denied: dict[str, object] = browser_post_reload(page=page)
    assert denied["status"] == 403
    assert denied["reason"] == test_case.expected_denied_reason
