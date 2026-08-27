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
    ReplayProgressBrowserE2ETestCase,
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
    assert plan_command == f"stb build {test_case.expected_command_suffix}"
    assert "--target" not in plan_command
    assert "--database" not in plan_command
    expect(page.get_by_text(f"$ {plan_command}", exact=True)).to_be_visible()
    replay_roots: list[dict[str, object]] = cast(
        list[dict[str, object]], selected_plan["replayRoots"]
    )
    assert replay_roots[0]["rowsToReplay"] is None
    expect(page.get_by_text("Replay roots", exact=True)).to_be_visible()
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/plan"
            and parse_qs(urlparse(response.url).query).get("counts") == ["true"]
        )
    ) as counted_plan_info:
        page.get_by_role("button", name="Load exact counts", exact=True).click()
    counted_plan: dict[str, object] = counted_plan_info.value.json()
    counted_replay_roots: list[dict[str, object]] = cast(
        list[dict[str, object]], counted_plan["replayRoots"]
    )
    assert counted_replay_roots[0]["rowsToReplay"] == test_case.expected_replay_rows
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
    assert {(urlparse(request.url).path, request.failure) for request in failed_requests} <= {
        ("/api/audit-scheduler", "net::ERR_ABORTED"),
        ("/api/definitions", "net::ERR_ABORTED"),
        ("/api/runs", "net::ERR_ABORTED"),
    }
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
    expected_command: re.Pattern[str] = re.compile(rf"stb build --select {test_case.selector}")
    expect(page.get_by_text(expected_command).first).to_be_visible()
    expect(
        page.locator(f'.svelte-flow__node[data-id="{test_case.expected_model_node_id}"]')
    ).to_be_visible()
    expect(page.get_by_text("run started", exact=True)).to_be_visible()
    expect(page.get_by_text("run completed", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Open in Plan", exact=True)).to_be_visible()
    statement_row: Locator = (
        page.locator("button[data-statement-sequence]")
        .filter(has_text=re.compile(rf"Replay source data.*{test_case.selector}"))
        .first
    )
    expect(statement_row).to_be_visible()
    with page.expect_response(
        lambda response: "/statements/" in urlparse(response.url).path
    ) as statement_info:
        statement_row.click()
    assert statement_info.value.status == 200
    statement_payload: dict[str, object] = cast(dict[str, object], statement_info.value.json())
    assert "runtime replay capture" not in str(statement_payload["sql"])
    assert "INSERT INTO" in str(statement_payload["sql"])
    expect(page.get_by_label("executed SQL", exact=True)).to_be_visible()
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
    expect(page.get_by_text("No failed builds.", exact=True)).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Succeeded\s+\d+$")).click()
    expect(run_link).to_be_visible()
    assert launch_invocation_id
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert {(urlparse(request.url).path, request.failure) for request in failed_requests} <= {
        ("/api/definitions", "net::ERR_ABORTED")
    }
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        ReplayProgressBrowserE2ETestCase(
            description="offset replay labels its approximate frontier estimate",
            statement_progress_fields={
                "replayOffsetProgress": {
                    "percentage": 60.0,
                    "etaSeconds": 20.0,
                    "completedSpan": 600,
                    "totalSpan": 1000,
                    "observedPartitions": 2,
                    "totalPartitions": 2,
                }
            },
            expected_progress_text="approximately 60.0% by replay offsets",
            expected_eta_count=1,
        ),
        ReplayProgressBrowserE2ETestCase(
            description="unsupported replay retains an honest indeterminate state",
            statement_progress_fields={},
            expected_progress_text="progress denominator unavailable",
            expected_eta_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_active_replay_when_viewing_run_then_frontier_progress_or_fallback_is_explicit(
    test_case: ReplayProgressBrowserE2ETestCase,
    running_plan_server: tuple[str, dict[str, object], Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    del browser_diagnostics
    base_url: str = running_plan_server[0]
    progress_payload: dict[str, object] = {
        "found": True,
        "queryId": "query-progress",
        "statementSequence": 4,
        "stepId": "replay_moving_orders",
        "phase": "replay",
        "observedAt": "2026-08-27 20:00:10.000",
        "elapsedSeconds": 10.0,
        "readRows": 16_700_000,
        "readBytes": 12_884_901_888,
        "totalRowsApprox": 272_477,
        "memoryUsageBytes": 3_865_470_566,
        "readRowsPerSecond": 1_670_000,
        "readBytesPerSecond": 1_288_490_188,
        "settings": {"max_memory_usage": "10000000000"},
        **test_case.statement_progress_fields,
    }
    feed_payload: dict[str, object] = {
        "found": True,
        "events": [
            {
                "event": "run_started",
                "sequence": 1,
                "emittedAt": "2026-08-27 20:00:00.000",
                "stepId": None,
                "phase": None,
                "displayCommand": "stb build --select moving_orders",
                "command": "build",
                "mode": "direct",
                "totalStatements": 6,
                "selectedNodeCount": 1,
            },
            {
                "event": "statement_started",
                "sequence": 2,
                "emittedAt": "2026-08-27 20:00:00.000",
                "statementSequence": 4,
                "stepId": "replay_moving_orders",
                "phase": "replay",
                "displayName": "Replay source data: moving_orders",
                "queryId": "query-progress",
            },
        ],
        "hasMore": False,
        "status": "running",
        "lastSignalAt": "2026-08-27 20:00:09.000",
        "lastSignalAgeSeconds": 1,
        "statementProgress": progress_payload,
    }
    page.route(
        "**/api/runs/mock-progress/events*",
        lambda route: route.fulfill(json=feed_payload),
    )
    page.route("**/api/runs", lambda route: route.fulfill(json=[]))
    page.route(
        "**/api/build/current*",
        lambda route: route.fulfill(
            json={
                "running": False,
                "invocationId": None,
                "currentInvocationId": None,
                "command": "",
                "exitCode": None,
                "events": [],
                "stderr": "",
                "forceAvailable": False,
            }
        ),
    )

    page.goto(f"{base_url}/runs/mock-progress", wait_until="domcontentloaded")

    progress: Locator = page.get_by_label("Active statement progress")
    expect(progress).to_contain_text(test_case.expected_progress_text, timeout=15_000)
    expect(progress).to_contain_text("16.7M")
    expect(progress.get_by_text("ETA 20s", exact=True)).to_have_count(test_case.expected_eta_count)
