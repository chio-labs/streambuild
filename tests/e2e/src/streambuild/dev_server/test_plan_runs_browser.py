import re
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

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
    Route,
    expect,
)

from tests.e2e.src.streambuild.dev_server._test_types import (
    BuildRunBrowserE2ETestCase,
    PlanBrowserE2ETestCase,
)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        PlanBrowserE2ETestCase(
            description="plan selection and replay remain URL-owned and pasteable",
            selector="moving_orders",
            expected_command_suffix="--select moving_orders",
            expected_replay_rows=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_retained_source_when_editing_plan_then_url_and_replay_contract_round_trips(
    test_case: PlanBrowserE2ETestCase,
    running_plan_server: tuple[str, dict[str, object], Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _readiness_payload, _log_path, _clickhouse_client, _database = running_plan_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics

    document_response: Response | None = page.goto(
        f"{base_url}/runs", wait_until="domcontentloaded", timeout=30_000
    )
    assert document_response is not None
    assert document_response.status == 200
    held_plan_requests: list[Route] = []
    plan_route_pattern: str = "**/api/plan?*"
    page.route(plan_route_pattern, lambda route: held_plan_requests.append(route))
    with page.expect_request(lambda request: urlparse(request.url).path == "/api/plan"):
        page.get_by_role("link", name="Plan", exact=True).click(no_wait_after=True)
    expect(page).to_have_url(re.compile(r"/plan$"))
    expect(page.get_by_role("combobox", name="What to rebuild")).to_be_visible()
    expect(page.get_by_test_id("plan-loading-state")).to_contain_text("Planning all models…")
    assert len(held_plan_requests) == 1
    held_plan_requests[0].continue_()
    page.unroute(plan_route_pattern)
    expect(page.get_by_test_id("plan-loading-state")).to_have_count(0, timeout=30_000)

    selector_input: Locator = page.get_by_role("combobox", name="What to rebuild")
    selector_input.fill(test_case.selector)
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/plan"
            and parse_qs(urlparse(response.url).query).get("select") == [test_case.selector]
        )
    ) as selected_plan_info:
        page.get_by_role("option", name=re.compile(rf"^{test_case.selector}\b")).click()
    selected_plan: dict[str, object] = selected_plan_info.value.json()

    expect(page).to_have_url(re.compile(rf"/plan\?select={test_case.selector}$"))
    expect(page.get_by_role("button", name=f"Remove {test_case.selector}")).to_be_visible()
    expect(page.get_by_text("1 selector", exact=True)).to_be_visible()
    plan_command: str = str(selected_plan["command"])
    assert plan_command.startswith("stb build --target test --database ")
    assert plan_command.endswith(test_case.expected_command_suffix)
    expect(page.get_by_text(f"$ {plan_command}", exact=True)).to_be_visible()
    replay_roots: list[dict[str, object]] = cast(
        list[dict[str, object]], selected_plan["replayRoots"]
    )
    assert replay_roots[0]["rowsToReplay"] == test_case.expected_replay_rows
    expect(page.get_by_text("Replay roots", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(rf"{test_case.expected_replay_rows} rows$"))).to_be_visible()

    from_time: Locator = page.get_by_role("button", name="From a time", exact=True)
    expect(from_time).to_be_enabled()
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/plan"
            and "start" in parse_qs(urlparse(response.url).query)
        )
    ):
        from_time.click()
    expect(page.get_by_label("Replay start time")).to_be_visible()
    bounded_url: str = page.url
    bounded_query: dict[str, list[str]] = parse_qs(urlparse(bounded_url).query)
    assert bounded_query["select"] == [test_case.selector]
    assert len(bounded_query["start"]) == 1
    replay_start: str = bounded_query["start"][0]
    expect(
        page.get_by_text(re.compile(rf"{re.escape(test_case.selector)}.*--start-time"))
    ).to_be_visible()

    page.reload(wait_until="domcontentloaded")
    expect(page).to_have_url(bounded_url)
    expect(page.get_by_label("Replay start time")).to_be_visible()
    expect(page.get_by_role("button", name=f"Remove {test_case.selector}")).to_be_visible()

    page.get_by_role("button", name=f"Remove {test_case.selector}").click()
    expect(page).to_have_url(re.compile(r"/plan$"))
    expect(page.get_by_role("button", name="From a time", exact=True)).to_be_disabled()
    expect(page.get_by_text("no selector — all models", exact=True)).to_be_visible()

    page.get_by_role("button", name="Preview a command", exact=True).click()
    page.get_by_placeholder("stb build --select pipeline:order_events").fill(
        f"stb build --select {test_case.selector} --start-time {replay_start}"
    )
    page.get_by_role("button", name="Preview", exact=True).click()
    expect(page).to_have_url(re.compile(rf"select={test_case.selector}.*start="))
    expect(
        page.get_by_text("Loaded 1 selector from the pasted command.", exact=True)
    ).to_be_visible()
    expect(page.get_by_label("Replay start time")).to_be_visible()
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        BuildRunBrowserE2ETestCase(
            description="plan execution reaches durable successful run history",
            selector="moving_orders",
            expected_start_status="starting",
            expected_outcome="succeeded",
            expected_model_node_id="model:moving_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_planned_model_when_executing_then_live_and_durable_run_surfaces_agree(
    test_case: BuildRunBrowserE2ETestCase,
    running_plan_server: tuple[str, dict[str, object], Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _readiness_payload, _log_path, _clickhouse_client, _database = running_plan_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics

    page.goto(
        f"{base_url}/plan?select={test_case.selector}",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    execute: Locator = page.get_by_role("button", name="Execute", exact=True)
    expect(execute).to_be_enabled(timeout=30_000)
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/build" and response.request.method == "POST"
        )
    ) as start_info:
        execute.click()
    start_payload: dict[str, object] = start_info.value.json()
    launch_invocation_id: str = str(start_payload["invocationId"])
    assert start_payload["status"] == test_case.expected_start_status
    expect(page).to_have_url(re.compile(r"/runs/[0-9a-f-]+\?live=1$"), timeout=30_000)

    expect(page.get_by_text(test_case.expected_outcome, exact=True).first).to_be_visible(
        timeout=120_000
    )
    final_path_parts: list[str] = urlparse(page.url).path.strip("/").split("/")
    assert final_path_parts[0] == "runs"
    final_invocation_id: str = final_path_parts[1]
    assert final_invocation_id
    expect(page.get_by_label("Run ID", exact=True)).to_have_text(final_invocation_id)
    expected_command: re.Pattern[str] = re.compile(rf"stb build .*--select {test_case.selector}")
    expect(page.get_by_text(expected_command).first).to_be_visible()
    expect(
        page.locator(f'.svelte-flow__node[data-id="{test_case.expected_model_node_id}"]')
    ).to_be_visible()
    expect(page.get_by_text("run started", exact=True)).to_be_visible()
    expect(page.get_by_text("run completed", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Open in Plan", exact=True)).to_be_visible()
    build_feed_response: APIResponse = page.request.get(f"{base_url}/api/build/current?after=0")
    assert build_feed_response.status == 200
    build_feed: dict[str, object] = cast(dict[str, object], build_feed_response.json())
    assert build_feed["invocationId"] == launch_invocation_id
    assert build_feed["currentInvocationId"] == final_invocation_id

    page.get_by_role("link", name="Open in Plan", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/plan\?select={test_case.selector}$"))
    expect(page.get_by_role("button", name=f"Remove {test_case.selector}")).to_be_visible()

    page.goto(f"{base_url}/runs", wait_until="domcontentloaded")
    run_link: Locator = page.locator(f'a[href="/runs/{final_invocation_id}"]')
    expect(run_link).to_be_visible(timeout=30_000)
    run_row: Locator = page.locator("tr").filter(has=run_link)
    expect(run_row).to_contain_text("Success")
    expect(run_row).to_contain_text(re.compile(rf"stb build .*--select {test_case.selector}"))
    page.get_by_role("button", name=re.compile(r"^Failed\s+\d+$")).click()
    expect(page.get_by_text("No failed runs.", exact=True)).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Succeeded\s+\d+$")).click()
    expect(run_link).to_be_visible()
    assert launch_invocation_id
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)
