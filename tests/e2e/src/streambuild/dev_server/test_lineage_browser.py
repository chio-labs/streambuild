from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import pytest
from playwright.sync_api import ConsoleMessage, Error, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import LineageBrowserE2ETestCase


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        LineageBrowserE2ETestCase(
            description="packaged lineage deep link renders real project and warehouse state",
            route="/lineage",
            expected_title="Lineage · StreamBuild",
            expected_query="",
            expected_source_node_id="source:order_events",
            expected_model_node_id="model:orders",
            expected_node_count=2,
            expected_edge_count=1,
        ),
        LineageBrowserE2ETestCase(
            description="parallel lineage server retains an isolated ungrouped route and state",
            route="/lineage?group=none",
            expected_title="Lineage · StreamBuild",
            expected_query="group=none",
            expected_source_node_id="source:order_events",
            expected_model_node_id="model:orders",
            expected_node_count=2,
            expected_edge_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_packaged_dev_server_when_opening_lineage_then_real_graph_renders(
    test_case: LineageBrowserE2ETestCase,
    running_lineage_server: tuple[str, dict[str, object], Path],
    browser_name: str,
    output_path: str,
    page: Page,
) -> None:
    base_url, readiness_payload, _log_path = running_lineage_server
    artifacts_path: Path = Path(output_path)
    console_messages: list[ConsoleMessage] = []
    page_errors: list[Error] = []
    failed_requests: list[Request] = []
    responses: list[Response] = []
    page.on("console", lambda message: console_messages.append(message))
    page.on("pageerror", lambda error: page_errors.append(error))
    page.on("requestfailed", lambda request: failed_requests.append(request))
    page.on("response", lambda response: responses.append(response))

    try:
        assert browser_name == "chromium"
        with page.expect_response(
            lambda response: urlparse(response.url).path == "/api/state"
        ) as state_response_info:
            document_response: Response | None = page.goto(
                f"{base_url}{test_case.route}",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        state_response: Response = state_response_info.value
        state_payload: dict[str, object] = state_response.json()
        models: dict[str, object] = cast(dict[str, object], state_payload["models"])
        sources: dict[str, object] = cast(dict[str, object], state_payload["sources"])
        readiness_models: dict[str, object] = cast(dict[str, object], readiness_payload["models"])
        readiness_sources: dict[str, object] = cast(dict[str, object], readiness_payload["sources"])

        assert document_response is not None
        assert document_response.status == 200
        assert state_response.status == 200
        assert set(state_payload) == {"capturedAt", "models", "sources"}
        assert set(models) == {"orders"}
        assert set(sources) == {"order_events"}
        assert set(readiness_models) == set(models)
        assert set(readiness_sources) == set(sources)
        assert urlparse(page.url).path == "/lineage"
        assert urlparse(page.url).query == test_case.expected_query
        expect(page).to_have_title(test_case.expected_title)
        expect(page.get_by_role("heading", name="Lineage", exact=True)).to_be_visible()
        expect(
            page.locator(f'.svelte-flow__node[data-id="{test_case.expected_source_node_id}"]')
        ).to_be_visible()
        expect(
            page.locator(f'.svelte-flow__node[data-id="{test_case.expected_model_node_id}"]')
        ).to_be_visible()
        expect(
            page.get_by_text(
                f"{test_case.expected_node_count} nodes · {test_case.expected_edge_count} edges",
                exact=True,
            )
        ).to_be_visible()
        assert all(message.type != "error" for message in console_messages)
        assert page_errors == []
        assert failed_requests == []
        assert all(response.status < 400 for response in responses)
    finally:
        artifacts_path.mkdir(parents=True, exist_ok=True)
        (artifacts_path / "browser-diagnostics.txt").write_text(
            "--- console ---\n"
            + "\n".join(f"{message.type}: {message.text}" for message in console_messages)
            + "\n--- page errors ---\n"
            + "\n".join(str(error) for error in page_errors)
            + "\n--- failed requests ---\n"
            + "\n".join(
                f"{request.method} {request.url} {request.failure}" for request in failed_requests
            )
            + "\n--- responses ---\n"
            + "\n".join(f"{response.status} {response.url}" for response in responses)
            + "\n",
            encoding="utf-8",
        )
