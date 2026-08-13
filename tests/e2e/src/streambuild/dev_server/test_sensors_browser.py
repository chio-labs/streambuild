from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from tests.e2e.src.streambuild.dev_server._test_types import SensorsBrowserE2ETestCase


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        SensorsBrowserE2ETestCase(
            description="sensors list, toggle, failed ticks, and dead letters are operable",
            expected_running_sensor="flaky_alerts",
            expected_paused_sensor="paused_watch",
            expected_dead_letter_fragment="simulated alert delivery failure",
            expected_tick_statuses=("dead_lettered", "failed"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_authored_sensors_when_browsing_then_lifecycle_is_visible_and_operable(
    test_case: SensorsBrowserE2ETestCase,
    running_sensors_browser_server: tuple[str, str, Path],
    page: Page,
) -> None:
    base_url, _database, _log_path = running_sensors_browser_server

    _ = page.goto(f"{base_url}/sensors")

    running_row: Locator = page.get_by_test_id(f"sensor-row-{test_case.expected_running_sensor}")
    expect(running_row).to_be_visible()
    expect(running_row).to_contain_text("running")
    expect(running_row).to_contain_text("dead_lettered")

    paused_row: Locator = page.get_by_test_id(f"sensor-row-{test_case.expected_paused_sensor}")
    expect(paused_row).to_contain_text("stopped")
    paused_row.get_by_role(
        "button", name=f"Toggle {test_case.expected_paused_sensor}", exact=True
    ).click()
    expect(paused_row).to_contain_text("running")
    expect(paused_row).to_contain_text("(override)")

    running_row.get_by_role("button", name=test_case.expected_running_sensor, exact=True).click()
    ticks_panel: Locator = page.get_by_test_id("sensor-ticks")
    expect(ticks_panel).to_be_visible()
    for status in test_case.expected_tick_statuses:
        expect(ticks_panel).to_contain_text(status)
    expect(ticks_panel).to_contain_text(test_case.expected_dead_letter_fragment)

    dead_letter_row: Locator = page.locator("div[data-testid^='dead-letter-']").first
    expect(dead_letter_row).to_be_visible()
    expect(dead_letter_row).to_contain_text(test_case.expected_dead_letter_fragment)

    page.get_by_label("Skip reason", exact=True).fill("acknowledged in browser test")
    dead_letter_row.get_by_role("button", name="Skip", exact=True).click()
    expect(page.locator("div[data-testid^='dead-letter-']")).to_have_count(0)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
