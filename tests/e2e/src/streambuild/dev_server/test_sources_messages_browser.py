import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import (
    MessageConsoleBrowserE2ETestCase,
    SourceTopicBrowserE2ETestCase,
)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        SourceTopicBrowserE2ETestCase(
            description="managed source and topic inventory remain cross-linked",
            source_name="order_events",
            expected_kind="managed Kafka",
            expected_retained_rows=12,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_managed_kafka_source_when_navigating_inventory_then_live_facts_remain_linked(
    test_case: SourceTopicBrowserE2ETestCase,
    running_message_browser_server: tuple[str, str, str, str, Path],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, topic, unmanaged_topic, _expected_full_value, _log_path = (
        running_message_browser_server
    )
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    document_response: Response | None = page.goto(
        f"{base_url}/sources", wait_until="domcontentloaded", timeout=30_000
    )
    assert document_response is not None
    assert document_response.status == 200
    source_link: Locator = page.get_by_role("link", name=test_case.source_name, exact=True)
    expect(source_link).to_be_visible(timeout=30_000)
    source_row: Locator = page.get_by_role("row").filter(has=source_link)
    source_cells: Locator = source_row.get_by_role("cell")
    expect(source_cells.nth(1)).to_have_text(test_case.expected_kind)
    expect(source_cells.nth(2)).to_have_text(topic)
    expect(source_cells.nth(7)).to_have_text(str(test_case.expected_retained_rows))

    source_link.click()
    expect(page).to_have_url(re.compile(rf"/sources/{test_case.source_name}$"))
    expect(page.get_by_role("link", name="Browse messages", exact=True)).to_have_attribute(
        "href", f"/sources/{test_case.source_name}/messages"
    )
    expect(page.get_by_role("columnheader", name="Partition", exact=True)).to_be_visible()
    partition_link: Locator = page.get_by_role("link", name="0", exact=True)
    expect(partition_link).to_have_attribute("title", "browse this partition's messages")
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/messages") and response.request.method == "POST"
        )
    ) as partition_info:
        partition_link.click()
    expect(page).to_have_url(re.compile(rf"/sources/{test_case.source_name}/messages\?q="))
    partition_query: list[str] = parse_qs(urlparse(page.url).query)["q"]
    assert len(partition_query) == 1
    expected_partition_mode: dict[str, object] = {
        "kind": "offsetRange",
        "partition": 0,
        "fromOffset": None,
        "toOffset": None,
    }
    assert json.loads(partition_query[0])["mode"] == expected_partition_mode
    partition_request: dict[str, object] = cast(
        dict[str, object], partition_info.value.request.post_data_json
    )
    assert partition_request["mode"] == expected_partition_mode
    expect(page.get_by_placeholder("partition")).to_have_value("0")
    expect(page.get_by_placeholder("from offset")).to_have_value("")
    expect(page.get_by_placeholder("to offset")).to_have_value("")

    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/topics"
    ) as info:
        page.goto(f"{base_url}/topics", wait_until="domcontentloaded")
    topics_payload: dict[str, object] = info.value.json()
    assert topics_payload["available"] is True
    topic_link: Locator = page.get_by_role("link", name=topic, exact=True)
    topic_row: Locator = page.get_by_role("row").filter(has=topic_link)
    topic_cells: Locator = topic_row.get_by_role("cell")
    expect(topic_cells.nth(3)).to_have_text(test_case.source_name)
    expect(topic_cells.nth(5)).to_have_text(str(test_case.expected_retained_rows))
    expect(page.get_by_text(unmanaged_topic, exact=True)).to_have_count(0)
    unmanaged_toggle: Locator = page.get_by_role(
        "checkbox", name="unmanaged topics (1)", exact=True
    )
    expect(unmanaged_toggle).to_be_visible(timeout=30_000)
    unmanaged_toggle.check()
    expect(page.get_by_text(unmanaged_topic, exact=True)).to_be_visible()
    page.get_by_placeholder("search topics…").fill(unmanaged_topic)
    expect(page.get_by_text(topic, exact=True)).to_have_count(0)
    page.get_by_placeholder("search topics…").fill("")
    topic_link.click()
    expect(page).to_have_url(re.compile(rf"/sources/{test_case.source_name}/messages$"))
    expect(page.get_by_role("button", name="Timestamp ▼", exact=True)).to_be_visible()
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        MessageConsoleBrowserE2ETestCase(
            description="message filters preview fields and full records round trip",
            source_name="order_events",
            filtered_order_id="order-02",
            expected_header_name="trace-id",
            expected_header_value="browser",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_landed_messages_when_filtering_console_then_shareable_record_evidence_is_exact(
    test_case: MessageConsoleBrowserE2ETestCase,
    running_message_browser_server: tuple[str, str, str, str, Path],
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, topic, _unmanaged_topic, expected_full_value, _log_path = (
        running_message_browser_server
    )
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    page.goto(
        f"{base_url}/sources/{test_case.source_name}/messages",
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    expect(page.get_by_text(re.compile(r"^12 messages ·"))).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="Timestamp ▼", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Landed at", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="P / Offset", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Key", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="Value", exact=True)).to_be_visible()

    page.get_by_role("button", name="Offset range", exact=True).click()
    expect(page.get_by_role("button", name="apply", exact=True)).to_be_disabled()
    page.get_by_placeholder("partition").fill("0")
    page.get_by_placeholder("from offset").fill("0")
    page.get_by_placeholder("to offset").fill("2")
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/messages") and response.request.method == "POST"
        )
    ) as offset_info:
        page.get_by_role("button", name="apply", exact=True).click()
    offset_request: dict[str, object] = cast(
        dict[str, object], offset_info.value.request.post_data_json
    )
    offset_mode: dict[str, object] = cast(dict[str, object], offset_request["mode"])
    assert offset_mode == {
        "kind": "offsetRange",
        "partition": 0,
        "fromOffset": 0,
        "toOffset": 2,
    }
    expect(page.get_by_text(re.compile(r"^3 messages ·"))).to_be_visible()
    for offset in range(3):
        expect(page.get_by_role("cell", name=f"0 / {offset}", exact=True)).to_be_visible()

    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/messages") and response.request.method == "POST"
        )
    ):
        page.get_by_role("button", name="Newest", exact=True).click()
    page.get_by_label("Facet path").fill("order_id")
    with page.expect_response(
        lambda response: urlparse(response.url).path.endswith("/messages/facets")
    ):
        with page.expect_response(
            lambda response: (
                urlparse(response.url).path.endswith("/messages")
                and response.request.method == "POST"
            )
        ):
            page.get_by_label("Facet path").press("Enter")
    facet: Locator = page.get_by_role(
        "button", name=re.compile(rf"^{test_case.filtered_order_id}\s+1$")
    )
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/messages") and response.request.method == "POST"
        )
    ):
        facet.click()
    expect(page).to_have_url(re.compile(r"/messages\?q="))
    shared_url: str = page.url
    encoded_query: list[str] = parse_qs(urlparse(shared_url).query)["q"]
    assert len(encoded_query) == 1
    expect(page.get_by_text(re.compile(r"^1 messages ·"))).to_be_visible()
    expect(page.get_by_text(test_case.filtered_order_id, exact=True).first).to_be_visible()

    page.get_by_placeholder("preview field, e.g. data.placer").fill("order_id")
    with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith("/messages") and response.request.method == "POST"
        )
    ) as preview_info:
        page.get_by_placeholder("preview field, e.g. data.placer").press("Enter")
    preview_request: dict[str, object] = cast(
        dict[str, object], preview_info.value.request.post_data_json
    )
    assert preview_request["previewPaths"] == [["order_id"]]
    preview_payload: dict[str, object] = preview_info.value.json()
    preview_rows: list[dict[str, object]] = cast(list[dict[str, object]], preview_payload["rows"])
    assert preview_rows[0]["previewValues"] == [test_case.filtered_order_id]
    expect(page.get_by_role("columnheader", name="order_id", exact=True)).to_be_visible()
    expect(page.get_by_role("columnheader", name="Value", exact=True)).to_be_visible()
    message_row: Locator = page.get_by_role("row").filter(
        has=page.get_by_role("cell", name="0 / 1", exact=True)
    )
    expect(message_row.get_by_role("cell").nth(3)).to_contain_text(test_case.filtered_order_id)
    expect(message_row.get_by_role("cell").nth(5)).to_have_text(test_case.filtered_order_id)
    with page.expect_response(
        lambda response: urlparse(response.url).path.endswith("/messages/record")
    ) as record_info:
        message_row.click()
    record_payload: dict[str, object] = record_info.value.json()
    assert record_info.value.status == 200
    assert record_payload["topic"] == topic
    assert record_payload["partition"] == 0
    assert record_payload["offset"] == 1
    assert record_payload["key"] == test_case.filtered_order_id
    assert record_payload["value"] == expected_full_value
    expect(page.get_by_role("button", name="Copy value", exact=True)).to_be_enabled()
    expect(page.get_by_text(re.compile(r"^full record unavailable"))).to_have_count(0)
    page.get_by_role("button", name="raw", exact=True).click()
    expect(page.locator("pre")).to_have_text(expected_full_value)
    page.get_by_role("button", name="headers (1)", exact=True).click()
    expect(page.get_by_text(test_case.expected_header_name, exact=True)).to_be_visible()
    expect(page.get_by_text(test_case.expected_header_value, exact=True)).to_be_visible()

    page.goto(shared_url, wait_until="domcontentloaded")
    expect(page.get_by_text(re.compile(r"^1 messages ·"))).to_be_visible(timeout=30_000)
    expect(page.get_by_text(test_case.filtered_order_id, exact=True).first).to_be_visible()
    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)
