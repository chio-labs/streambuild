from pathlib import Path

import pytest
from playwright.sync_api import (
    ConsoleMessage,
    Error,
    Locator,
    Page,
    Request,
    Response,
    Route,
    expect,
)

from tests.e2e.src.streambuild.dev_server._test_types import (
    PlanSourceRecreationBrowserE2ETestCase,
)
from tests.e2e.src.streambuild.dev_server.helpers import (
    SOURCE_RECREATION,
    SOURCE_RECREATION_MESSAGE,
    build_source_recreation_plan_payload,
)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        PlanSourceRecreationBrowserE2ETestCase(
            description="a structured recreation is a change, not a planner warning",
            source_recreations=(SOURCE_RECREATION,),
            expected_section_count=1,
            expected_section_fragments=(
                "Sources recreated",
                "kafka__orders",
                "mv__orders",
                "raw__orders",
                "rows kept",
                "kafka_topic_list",
                "kafka_max_block_size",
                "pipeline:pl__moving_events",
                "pl__order_audit keep reading raw__orders",
            ),
            expected_summary_fragment="· 1 source recreated",
            expected_warning_count=0,
        ),
        PlanSourceRecreationBrowserE2ETestCase(
            description="an older server's recreation warning stays visible",
            source_recreations=(),
            expected_section_count=0,
            expected_section_fragments=(),
            expected_summary_fragment="1 for source drift",
            expected_warning_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_planned_source_recreation_when_viewing_plan_then_it_is_listed_as_a_change(
    test_case: PlanSourceRecreationBrowserE2ETestCase,
    running_disconnected_browser_server: tuple[str, Path, Path],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _project_dir, _log_path = running_disconnected_browser_server
    _console_messages, page_errors, _failed_requests, _responses = browser_diagnostics
    payload: dict[str, object] = build_source_recreation_plan_payload(
        source_recreations=list(test_case.source_recreations)
    )

    def fulfill_plan(route: Route) -> None:
        route.fulfill(json=payload)

    page.route("**/api/plan?*", fulfill_plan)
    page.route("**/api/plan", fulfill_plan)

    assert page.goto(f"{base_url}/plan?changed=1", wait_until="domcontentloaded") is not None
    expect(page.get_by_test_id("plan-build-mode")).to_have_text("direct", timeout=30_000)
    section: Locator = page.get_by_test_id("plan-source-recreations")
    expect(section).to_have_count(test_case.expected_section_count)
    for fragment in test_case.expected_section_fragments:
        expect(section).to_contain_text(fragment)
    expect(page.get_by_text(test_case.expected_summary_fragment, exact=False)).to_be_visible()
    expect(page.get_by_text("Planner warnings", exact=True)).to_have_count(
        test_case.expected_warning_count
    )
    expect(page.get_by_text(SOURCE_RECREATION_MESSAGE, exact=True)).to_have_count(
        test_case.expected_warning_count
    )
    expect(page.get_by_text("source drift", exact=True)).to_be_visible()
    assert page_errors == []
