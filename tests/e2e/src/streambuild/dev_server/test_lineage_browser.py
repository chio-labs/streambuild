import re
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import (
    LineageApproximateActivityE2ETestCase,
    LineageExactActivityE2ETestCase,
    RunCommandBoxE2ETestCase,
)
from tests.e2e.src.streambuild.dev_server.helpers import seed_lineage_exact_activity

_FLOW_ANIMATION_SETTLE_MS: int = 350


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        RunCommandBoxE2ETestCase(
            description="completes supported options while preserving pinned context",
            protected_model="moving_orders",
            expected_confirmation="DEPLOY_MOVING_EVENTS",
            expected_quoted_selector="pipeline:order events",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_run_command_box_when_editing_then_completes_only_pinned_context_options(
    test_case: RunCommandBoxE2ETestCase,
    running_lineage_server: tuple[str, dict[str, object], Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _readiness_payload, _log_path, _clickhouse_client, _database = running_lineage_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    page.goto(f"{base_url}/lineage?group=none", wait_until="domcontentloaded", timeout=30_000)
    page.locator(f'.svelte-flow__node[data-id="model:{test_case.protected_model}"]').click(
        position={"x": 20, "y": 20}
    )
    page.get_by_role("button", name="Execute", exact=True).click()
    run_dialog: Locator = page.get_by_role("dialog", name="Run")
    command: Locator = run_dialog.get_by_role("combobox", name="Build command")
    run_button: Locator = run_dialog.get_by_role("button", name="Run", exact=True)

    command.fill("stb build --target prod")
    expect(run_dialog.get_by_role("alert")).to_contain_text(
        "--target is fixed by stb dev and cannot be overridden from the UI"
    )
    expect(run_button).to_be_disabled()

    command.fill(f"stb build --select '{test_case.expected_quoted_selector}' --auto-approve")
    expect(run_dialog.get_by_role("alert")).to_have_count(0)
    expect(run_dialog.get_by_text(test_case.expected_quoted_selector, exact=True)).to_be_visible()

    command.fill("stb build --sel")
    expect(run_dialog.get_by_role("option", name=re.compile(r"^--select"))).to_be_visible()
    command.press("ArrowDown")
    command.press("Enter")
    expect(command).to_have_value("stb build --select ")

    selector_command: str = "stb build --select mov --auto-approve"
    selector_cursor: int = selector_command.index("mov") + len("mov")
    command.fill(selector_command)
    command.evaluate(
        "(element, cursor) => { element.setSelectionRange(cursor, cursor); "
        "element.dispatchEvent(new Event('select', { bubbles: true })); }",
        selector_cursor,
    )
    run_dialog.get_by_role("option", name=re.compile(rf"^{test_case.protected_model}\b")).click()
    expect(command).to_have_value(f"stb build --select {test_case.protected_model} --auto-approve")

    confirmation_command: str = (
        f"stb build --select {test_case.protected_model} --confirm DEP --auto-approve"
    )
    confirmation_cursor: int = confirmation_command.index("DEP") + len("DEP")
    command.fill(confirmation_command)
    command.evaluate(
        "(element, cursor) => { element.setSelectionRange(cursor, cursor); "
        "element.dispatchEvent(new Event('select', { bubbles: true })); }",
        confirmation_cursor,
    )
    confirmation: Locator = run_dialog.get_by_role(
        "option", name=re.compile(rf"^{test_case.expected_confirmation}\b")
    )
    expect(confirmation).to_be_visible()
    confirmation.click()
    expect(command).to_have_value(
        f"stb build --select {test_case.protected_model} "
        f"--confirm {test_case.expected_confirmation} --auto-approve"
    )
    expect(run_button).to_be_enabled()
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        LineageExactActivityE2ETestCase(
            description="logged activity updates lineage, inspector, routing, and exact selections",
            expected_title="Lineage · StreamBuild",
            expected_logical_counts="6 nodes · 3 edges",
            expected_physical_counts="3 nodes · 2 edges",
            expected_multi_command="stb build --select idle_orders moving_orders --auto-approve",
            expected_model_only_command="stb build --select moving_orders --auto-approve",
            expected_moving_state="moving",
            expected_idle_state="idle",
            expected_stalled_state="stalled",
            expected_source="query_views_log",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_logged_activity_when_using_lineage_then_live_semantics_remain_truthful(
    test_case: LineageExactActivityE2ETestCase,
    running_lineage_server: tuple[str, dict[str, object], Path, Client, str],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    browser_name: str,
    page: Page,
) -> None:
    base_url, readiness_payload, _log_path, clickhouse_client, database = running_lineage_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    page.clock.install()

    assert browser_name == "chromium"
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/state"
    ) as initial_state_info:
        document_response: Response | None = page.goto(
            f"{base_url}/lineage?group=none",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
    initial_state: dict[str, object] = initial_state_info.value.json()
    initial_models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], initial_state["models"]
    )
    initial_sources: dict[str, object] = cast(dict[str, object], initial_state["sources"])

    assert document_response is not None
    assert document_response.status == 200
    assert set(initial_state) == {"capturedAt", "models", "sources"}
    assert set(initial_models) == {"idle_orders", "moving_orders", "stalled_orders"}
    assert set(initial_sources) == {"idle_events", "moving_events", "stalled_events"}
    assert set(cast(dict[str, object], readiness_payload["models"])) == set(initial_models)
    assert all(
        cast(dict[str, object], model["activity"])["state"] == "idle"
        for model in initial_models.values()
    )
    expect(page).to_have_title(test_case.expected_title)
    expect(page.get_by_text(test_case.expected_logical_counts, exact=True)).to_be_visible()

    moving_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="source:moving_events->model:moving_orders:driving_input"]'
    )
    expect(moving_edge).to_have_attribute("data-ref-type", "driving_input")
    expect(moving_edge).to_have_attribute("data-flow-state", "unknown")
    assert "sb-edge-driving" in str(moving_edge.get_attribute("class"))

    viewport: Locator = page.locator(".svelte-flow__viewport")
    canvas_box: dict[str, float] = cast(
        dict[str, float], page.get_by_test_id("lineage-canvas").bounding_box()
    )
    page.mouse.move(
        canvas_box["x"] + canvas_box["width"] / 2,
        canvas_box["y"] + canvas_box["height"] / 2,
    )
    zoom_before_wheel: float = viewport.evaluate(
        "element => new DOMMatrix(getComputedStyle(element).transform).a"
    )
    page.mouse.wheel(0, -500)
    page.wait_for_timeout(100)
    assert (
        viewport.evaluate("element => new DOMMatrix(getComputedStyle(element).transform).a")
        == zoom_before_wheel
    )
    page.keyboard.down("Control")
    page.mouse.wheel(0, -500)
    page.keyboard.up("Control")
    page.wait_for_timeout(_FLOW_ANIMATION_SETTLE_MS)
    zoom_after_control_wheel: float = viewport.evaluate(
        "element => new DOMMatrix(getComputedStyle(element).transform).a"
    )
    assert zoom_after_control_wheel != zoom_before_wheel
    page.mouse.wheel(0, -500)
    page.wait_for_timeout(100)
    assert (
        viewport.evaluate("element => new DOMMatrix(getComputedStyle(element).transform).a")
        == zoom_after_control_wheel
    )
    page.get_by_role("button", name="Fit view", exact=True).click()

    page.get_by_role("button", name="Boxes", exact=True).click()
    expect(page).to_have_url(re.compile(r"/lineage\?group=boxes$"))
    page.goto(f"{base_url}/lineage?group=none&q=moving", wait_until="domcontentloaded")
    page.get_by_role("button", name="Physical", exact=True).click()
    expect(page).to_have_url(
        re.compile(r"group=none.*q=moving.*mode=physical|mode=physical.*group=none.*q=moving")
    )
    expect(page.get_by_text(test_case.expected_physical_counts, exact=True)).to_be_visible()
    page.get_by_role("button", name="Logical", exact=True).click()
    expect(page).to_have_url(re.compile(r"/lineage\?group=none&q=moving$"))
    page.goto(f"{base_url}/lineage?group=none", wait_until="domcontentloaded")

    moving_node: Locator = page.locator('.svelte-flow__node[data-id="model:moving_orders"]')
    idle_node: Locator = page.locator('.svelte-flow__node[data-id="model:idle_orders"]')
    source_node: Locator = page.locator('.svelte-flow__node[data-id="source:moving_events"]')
    moving_node.click(position={"x": 20, "y": 20})
    page.get_by_role("button", name="Fit view", exact=True).click()
    idle_node.click(position={"x": 20, "y": 20}, modifiers=["Control"])
    assert "selected" in str(moving_node.get_attribute("class"))
    assert "selected" in str(idle_node.get_attribute("class"))
    page.get_by_role("button", name="Execute", exact=True).click()
    run_dialog: Locator = page.get_by_role("dialog", name="Run")
    expect(run_dialog.get_by_label("Build command")).to_have_value(test_case.expected_multi_command)
    run_dialog.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Close inspector").click()

    moving_node.click(position={"x": 20, "y": 20})
    page.get_by_role("button", name="Fit view", exact=True).click()
    idle_node.click(position={"x": 20, "y": 20}, modifiers=["Meta"])
    assert "selected" in str(moving_node.get_attribute("class"))
    assert "selected" in str(idle_node.get_attribute("class"))
    page.get_by_role("button", name="Close inspector").click()
    moving_node.click(position={"x": 20, "y": 20})
    page.get_by_role("button", name="Fit view", exact=True).click()
    idle_node.click(position={"x": 20, "y": 20}, modifiers=["Shift"])
    assert "selected" in str(moving_node.get_attribute("class"))
    assert "selected" in str(idle_node.get_attribute("class"))
    page.get_by_role("button", name="Close inspector").click()

    page.wait_for_timeout(_FLOW_ANIMATION_SETTLE_MS)
    viewport_before_source_click: str = viewport.evaluate(
        "element => getComputedStyle(element).transform"
    )
    source_node.click(position={"x": 20, "y": 20})
    page.wait_for_timeout(_FLOW_ANIMATION_SETTLE_MS)
    assert (
        viewport.evaluate("element => getComputedStyle(element).transform")
        == viewport_before_source_click
    )
    page.get_by_role("button", name="Fit view", exact=True).click()
    moving_node.click(position={"x": 20, "y": 20}, modifiers=["Control"])
    page.get_by_role("button", name="Execute", exact=True).click()
    run_dialog = page.get_by_role("dialog", name="Run")
    expect(run_dialog.get_by_label("Build command")).to_have_value(
        test_case.expected_model_only_command
    )
    run_dialog.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Close inspector").click()

    page.get_by_role("button", name="Physical", exact=True).click()
    physical_mv: Locator = page.locator('.svelte-flow__node[data-id="rel:mv__moving_orders"]')
    physical_table: Locator = page.locator('.svelte-flow__node[data-id="rel:tbl__moving_orders"]')
    physical_mv.click(position={"x": 20, "y": 20})
    page.get_by_role("button", name="Fit view", exact=True).click()
    physical_table.click(position={"x": 20, "y": 20}, modifiers=["Control"])
    page.get_by_role("button", name="Execute", exact=True).click()
    run_dialog = page.get_by_role("dialog", name="Run")
    expect(run_dialog.get_by_label("Build command")).to_have_value(
        test_case.expected_model_only_command
    )
    run_dialog.get_by_role("button", name="Close", exact=True).click()
    page.get_by_role("button", name="Close inspector").click()
    page.get_by_role("button", name="Logical", exact=True).click()

    moving_node = page.locator('.svelte-flow__node[data-id="model:moving_orders"]')
    moving_node.click(position={"x": 20, "y": 20})
    seed_lineage_exact_activity(client=clickhouse_client, database=database)
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/state"
    ) as polled_state_info:
        page.clock.run_for(30_000)
    polled_state: dict[str, object] = polled_state_info.value.json()
    polled_models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], polled_state["models"]
    )
    moving_activity: dict[str, object] = cast(
        dict[str, object], polled_models["moving_orders"]["activity"]
    )
    idle_activity: dict[str, object] = cast(
        dict[str, object], polled_models["idle_orders"]["activity"]
    )
    stalled_activity: dict[str, object] = cast(
        dict[str, object], polled_models["stalled_orders"]["activity"]
    )

    assert moving_activity["state"] == test_case.expected_moving_state
    assert idle_activity["state"] == test_case.expected_idle_state
    assert stalled_activity["state"] == test_case.expected_stalled_state
    assert moving_activity["source"] == test_case.expected_source
    assert idle_activity["source"] == test_case.expected_source
    assert stalled_activity["source"] == test_case.expected_source
    assert "selected" in str(moving_node.get_attribute("class"))
    activity_panel: Locator = page.get_by_test_id("lineage-activity")
    expect(activity_panel).to_have_attribute("data-state", test_case.expected_moving_state)
    expect(activity_panel).to_have_attribute("data-source", test_case.expected_source)
    page.get_by_role("button", name="Close inspector").click()

    moving_edge = page.locator(
        '.svelte-flow__edge[data-id="source:moving_events->model:moving_orders:driving_input"]'
    )
    idle_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="source:idle_events->model:idle_orders:driving_input"]'
    )
    stalled_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="source:stalled_events->model:stalled_orders:driving_input"]'
    )
    expect(moving_edge).to_have_attribute("data-flow-state", "flowing")
    expect(idle_edge).to_have_attribute("data-flow-state", "unknown")
    expect(stalled_edge).to_have_attribute("data-flow-state", "stalled")
    assert "sb-edge-driving-flowing" in str(moving_edge.get_attribute("class"))
    assert "sb-edge-driving-stalled" in str(stalled_edge.get_attribute("class"))
    assert (
        moving_edge.locator("path.svelte-flow__edge-path").evaluate(
            "element => getComputedStyle(element).animationName"
        )
        == "sbflow"
    )
    assert (
        idle_edge.locator("path.svelte-flow__edge-path").evaluate(
            "element => getComputedStyle(element).animationName"
        )
        == "none"
    )
    assert (
        stalled_edge.locator("path.svelte-flow__edge-path").evaluate(
            "element => getComputedStyle(element).animationName"
        )
        == "none"
    )

    page.locator('.svelte-flow__node[data-id="model:stalled_orders"]').click(
        position={"x": 20, "y": 20}
    )
    expect(page.get_by_test_id("lineage-activity")).to_have_attribute(
        "data-state", test_case.expected_stalled_state
    )
    expect(page.get_by_test_id("lineage-activity")).to_contain_text(
        "The latest materialized-view execution failed."
    )
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        LineageApproximateActivityE2ETestCase(
            description="missing ClickHouse logs render approximate movement and unknown honestly",
            expected_counts="6 nodes · 3 edges",
            expected_moving_state="moving",
            expected_unknown_state="unknown",
            expected_moving_source="system_parts",
            expected_unknown_source="unavailable",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_activity_logs_when_opening_lineage_then_evidence_remains_honest(
    test_case: LineageApproximateActivityE2ETestCase,
    running_no_activity_log_lineage_server: tuple[str, dict[str, object], Path],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, readiness_payload, _log_path = running_no_activity_log_lineage_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/state"
    ) as state_response_info:
        document_response: Response | None = page.goto(
            f"{base_url}/lineage?group=none",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
    state_payload: dict[str, object] = state_response_info.value.json()
    models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], state_payload["models"]
    )
    moving_activity: dict[str, object] = cast(
        dict[str, object], models["moving_orders"]["activity"]
    )
    unknown_activity: dict[str, object] = cast(dict[str, object], models["idle_orders"]["activity"])

    assert document_response is not None
    assert document_response.status == 200
    assert set(cast(dict[str, object], readiness_payload["models"])) == set(models)
    assert moving_activity["state"] == test_case.expected_moving_state
    assert moving_activity["source"] == test_case.expected_moving_source
    assert moving_activity["approximate"] is True
    assert moving_activity["lastTriggeredAt"] is None
    assert moving_activity["rowsWritten"] == 0
    assert unknown_activity["state"] == test_case.expected_unknown_state
    assert unknown_activity["source"] == test_case.expected_unknown_source
    assert unknown_activity["sourceAvailable"] is False
    expect(page.get_by_text(test_case.expected_counts, exact=True)).to_be_visible()

    moving_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="source:moving_events->model:moving_orders:driving_input"]'
    )
    unknown_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="source:idle_events->model:idle_orders:driving_input"]'
    )
    expect(moving_edge).to_have_attribute("data-flow-state", "flowing")
    expect(unknown_edge).to_have_attribute("data-flow-state", "unknown")
    page.locator('.svelte-flow__node[data-id="model:moving_orders"]').click(
        position={"x": 20, "y": 20}
    )
    activity_panel: Locator = page.get_by_test_id("lineage-activity")
    expect(activity_panel).to_have_attribute("data-state", test_case.expected_moving_state)
    expect(activity_panel).to_have_attribute("data-source", test_case.expected_moving_source)
    expect(activity_panel).to_have_attribute("data-approximate", "true")
    expect(activity_panel).to_contain_text("system_parts (approximate)")
    expect(activity_panel.get_by_text("Last write", exact=True)).to_be_visible()
    expect(activity_panel.get_by_text("Last trigger", exact=True)).to_have_count(0)
    expect(activity_panel.get_by_text("Recent writes", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Close inspector").click()
    page.locator('.svelte-flow__node[data-id="model:idle_orders"]').click(
        position={"x": 20, "y": 20}
    )
    activity_panel = page.get_by_test_id("lineage-activity")
    expect(activity_panel).to_have_attribute("data-state", test_case.expected_unknown_state)
    expect(activity_panel).to_have_attribute("data-source", test_case.expected_unknown_source)
    expect(activity_panel).to_contain_text("ClickHouse activity telemetry is unavailable.")
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)
