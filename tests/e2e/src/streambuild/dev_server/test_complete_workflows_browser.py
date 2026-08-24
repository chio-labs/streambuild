import re
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import (
    CompleteStreamingBrowserE2ETestCase,
    UnsafeReplayBrowserE2ETestCase,
)
from tests.e2e.src.streambuild.executor.helpers import (
    build_kafka_producer,
    produce_kafka_messages,
    wait_for_query_view_activity,
    wait_for_row_count,
    wait_for_state_model_activity,
)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        CompleteStreamingBrowserE2ETestCase(
            description="Redpanda message reaches final lineage evidence",
            message_key="message-key-11",
            message_value='{"order_id":"order-11"}',
            expected_order_id="order-11",
            expected_final_order_id="enriched:order-11",
            expected_activity_source="query_views_log",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_kafka_message_when_models_land_then_lineage_renders_exact_activity(
    test_case: CompleteStreamingBrowserE2ETestCase,
    running_complete_streaming_browser_server: tuple[str, str, str, Path],
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, topic, bootstrap_server, _log_path = running_complete_streaming_browser_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/state"
    ) as state_info:
        document_response: Response | None = page.goto(
            f"{base_url}/lineage?group=none", wait_until="domcontentloaded", timeout=30_000
        )
    assert document_response is not None
    assert document_response.status == 200
    initial_state: dict[str, object] = state_info.value.json()
    initial_models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], initial_state["models"]
    )
    assert set(initial_models) == {"orders", "orders_enriched"}
    assert cast(dict[str, object], initial_models["orders_enriched"]["activity"])["state"] == "idle"
    expect(page.get_by_text("3 nodes · 2 edges", exact=True)).to_be_visible()
    final_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="model:orders->model:orders_enriched:driving_input"]'
    )
    expect(final_edge).to_have_attribute("data-flow-state", "unknown")

    producer: KafkaProducer = build_kafka_producer(bootstrap_server=bootstrap_server)
    try:
        produce_kafka_messages(
            producer=producer,
            topic=topic,
            messages=((test_case.message_key, test_case.message_value),),
        )
    finally:
        producer.close()
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name="tbl__orders_enriched",
        expected_count=1,
    )
    activity_observation: tuple[str, int] = wait_for_query_view_activity(
        client=e2e_clickhouse_client,
        database=e2e_clickhouse_database,
        relation_name="tbl__orders_enriched",
        expected_rows=1,
    )
    assert activity_observation == ("QueryFinish", 1)
    raw_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT kafka_key, kafka_value FROM {e2e_clickhouse_database}.raw__order_events "
            "ORDER BY _replay_offset"
        ).result_rows
    )
    order_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {e2e_clickhouse_database}.tbl__orders"
        ).result_rows
    )
    final_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {e2e_clickhouse_database}.tbl__orders_enriched"
        ).result_rows
    )
    assert raw_rows == ((test_case.message_key, test_case.message_value),)
    assert order_rows == ((test_case.expected_order_id,),)
    assert final_rows == ((test_case.expected_final_order_id,),)
    ready_state: dict[str, object] = wait_for_state_model_activity(
        base_url=base_url,
        model_name="orders_enriched",
        expected_state="moving",
    )
    polled_models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], ready_state["models"]
    )
    final_activity: dict[str, object] = cast(
        dict[str, object], polled_models["orders_enriched"]["activity"]
    )
    assert final_activity["state"] == "moving"
    assert final_activity["source"] == test_case.expected_activity_source
    assert final_activity["sourceAvailable"] is True
    assert final_activity["approximate"] is False
    assert final_activity["rowsWritten"] == 1

    with page.expect_response(lambda response: urlparse(response.url).path == "/api/state"):
        page.get_by_role("button", name="Refresh snapshot", exact=True).click()
    expect(final_edge).to_have_attribute("data-flow-state", "flowing")
    assert "sb-edge-driving-flowing" in str(final_edge.get_attribute("class"))
    assert (
        final_edge.locator("path.svelte-flow__edge-path").evaluate(
            "element => getComputedStyle(element).animationName"
        )
        == "sbflow"
    )
    page.locator('.svelte-flow__node[data-id="model:orders_enriched"]').click(
        position={"x": 20, "y": 20}
    )
    activity_panel: Locator = page.get_by_test_id("lineage-activity")
    expect(activity_panel).to_have_attribute("data-state", "moving")
    expect(activity_panel).to_have_attribute("data-source", test_case.expected_activity_source)
    expect(activity_panel).to_contain_text("1 rows were written in the last 120s.")
    page.get_by_role("button", name="Close inspector").click()
    page.get_by_role("button", name="Physical", exact=True).click()
    expect(page.get_by_text("7 nodes · 6 edges", exact=True)).to_be_visible()
    for relation_name in (
        "kafka__order_events",
        "mv__order_events",
        "raw__order_events",
        "mv__orders",
        "tbl__orders",
        "mv__orders_enriched",
        "tbl__orders_enriched",
    ):
        expect(page.locator(f'.svelte-flow__node[data-id="rel:{relation_name}"]')).to_be_visible()
    physical_edge: Locator = page.locator(
        '.svelte-flow__edge[data-id="rel:tbl__orders->rel:mv__orders_enriched:driving_input"]'
    )
    expect(physical_edge).to_have_attribute("data-flow-state", "flowing")
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        UnsafeReplayBrowserE2ETestCase(
            description="unsafe child replay rejects before teardown and upstream rebuild recovers",
            unsafe_selector="derived_moving_orders",
            safe_selector="moving_orders",
            expected_missing_column="_replay_timestamp",
            expected_preserved_row="catalog-42",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incompatible_replay_input_when_planning_then_rejects_and_safe_rebuild_recovers(
    test_case: UnsafeReplayBrowserE2ETestCase,
    running_catalog_pipeline_browser_server: tuple[str, dict[str, object], str, Path],
    e2e_clickhouse_client: Client,
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, _state_payload, database, _log_path = running_catalog_pipeline_browser_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    e2e_clickhouse_client.command(f"DROP VIEW {database}.mv__derived_moving_orders SYNC")
    e2e_clickhouse_client.command(
        f"ALTER TABLE {database}.tbl__moving_orders DROP COLUMN {test_case.expected_missing_column}"
    )
    relation_names: str = (
        "'browser_moving_events', 'mv__moving_orders', 'tbl__moving_orders', "
        "'mv__derived_moving_orders', 'tbl__derived_moving_orders'"
    )
    objects_before: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            "SELECT name, toString(uuid), create_table_query FROM system.tables "
            f"WHERE database = '{database}' AND name IN ({relation_names}) ORDER BY name"
        ).result_rows
    )
    source_rows_before: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.browser_moving_events ORDER BY order_id"
        ).result_rows
    )
    parent_rows_before: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__moving_orders ORDER BY order_id"
        ).result_rows
    )
    child_rows_before: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__derived_moving_orders ORDER BY order_id"
        ).result_rows
    )
    invocation_count_before: int = int(
        e2e_clickhouse_client.query(
            f"SELECT count() FROM {database}._streambuild_invocations"
        ).result_rows[0][0]
    )
    assert source_rows_before == ((test_case.expected_preserved_row,),)
    assert parent_rows_before == source_rows_before
    assert child_rows_before == source_rows_before

    page.goto(f"{base_url}/plan", wait_until="domcontentloaded", timeout=30_000)
    selector_input: Locator = page.get_by_role("combobox", name="What to rebuild")
    selector_input.fill(test_case.unsafe_selector)
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/plan"
            and parse_qs(urlparse(response.url).query).get("select") == [test_case.unsafe_selector]
            and response.status == 400
        )
    ) as rejected_info:
        page.get_by_role("option", name=re.compile(rf"^{test_case.unsafe_selector}\b")).click()
    rejection_payload: dict[str, object] = rejected_info.value.json()
    rejection_detail: str = str(rejection_payload["detail"])
    assert test_case.unsafe_selector in rejection_detail
    assert "tbl__moving_orders" in rejection_detail
    assert test_case.expected_missing_column in rejection_detail
    assert "Rebuild the upstream scope" in rejection_detail
    expect(page.get_by_text(rejection_detail, exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Execute", exact=True)).to_be_disabled()
    assert all(
        not (urlparse(response.url).path == "/api/build" and response.request.method == "POST")
        for response in responses
    )

    objects_after_rejection: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            "SELECT name, toString(uuid), create_table_query FROM system.tables "
            f"WHERE database = '{database}' AND name IN ({relation_names}) ORDER BY name"
        ).result_rows
    )
    parent_rows_after_rejection: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__moving_orders ORDER BY order_id"
        ).result_rows
    )
    child_rows_after_rejection: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__derived_moving_orders ORDER BY order_id"
        ).result_rows
    )
    invocation_count_after_rejection: int = int(
        e2e_clickhouse_client.query(
            f"SELECT count() FROM {database}._streambuild_invocations"
        ).result_rows[0][0]
    )
    assert objects_after_rejection == objects_before
    assert parent_rows_after_rejection == parent_rows_before
    assert child_rows_after_rejection == child_rows_before
    assert invocation_count_after_rejection == invocation_count_before

    page.get_by_role("button", name=f"Remove {test_case.unsafe_selector}").click()
    selector_input.fill(test_case.safe_selector)
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/plan"
            and parse_qs(urlparse(response.url).query).get("select") == [test_case.safe_selector]
            and response.status == 200
        )
    ) as safe_plan_info:
        page.get_by_role("option", name=re.compile(rf"^{test_case.safe_selector}\b")).click()
    safe_plan: dict[str, object] = safe_plan_info.value.json()
    assert safe_plan["userScope"] == [test_case.safe_selector]
    expect(page.get_by_text(rejection_detail, exact=True)).to_have_count(0)
    execute: Locator = page.get_by_role("button", name="Execute", exact=True)
    expect(execute).to_be_enabled()
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == "/api/build" and response.request.method == "POST"
        )
    ) as start_info:
        execute.click()
    assert start_info.value.status == 200
    assert start_info.value.json()["status"] == "starting"
    expect(page).to_have_url(re.compile(r"/runs/[0-9a-f-]+\?live=1$"), timeout=30_000)
    expect(page.get_by_text("succeeded", exact=True).first).to_be_visible(timeout=120_000)
    expect(page.get_by_text("run completed", exact=True)).to_be_visible()

    repaired_columns: tuple[str, ...] = tuple(
        str(row[0])
        for row in e2e_clickhouse_client.query(
            "SELECT name FROM system.columns "
            f"WHERE database = '{database}' AND table = 'tbl__moving_orders' ORDER BY position"
        ).result_rows
    )
    assert test_case.expected_missing_column in repaired_columns
    e2e_clickhouse_client.command(
        f"INSERT INTO {database}.browser_moving_events (order_id, event_timestamp) "
        "VALUES ('catalog-43', now64(3))"
    )
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=database,
        table_name="tbl__derived_moving_orders",
        expected_count=2,
    )
    recovered_rows: tuple[str, ...] = tuple(
        str(row[0])
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.tbl__derived_moving_orders ORDER BY order_id"
        ).result_rows
    )
    assert recovered_rows == (test_case.expected_preserved_row, "catalog-43")
    assert all(
        message.type != "error" or "400 (Bad Request)" in message.text
        for message in console_messages
    )
    assert page_errors == []
    assert all(
        urlparse(request.url).path == "/api/plan"
        and not parse_qs(urlparse(request.url).query).get("select")
        and request.failure == "net::ERR_ABORTED"
        for request in failed_requests
    )
    assert all(
        response.status < 400
        or (response.status == 400 and urlparse(response.url).path == "/api/plan")
        for response in responses
    )
