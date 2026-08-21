from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import DeploymentBrowserE2ETestCase


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        DeploymentBrowserE2ETestCase(
            description="persisted deployment drift replaces cleanly across detail routes",
            expected_changed_model="customer_orders",
            expected_active_value="Ada",
            expected_staged_value="Ada!",
            missing_deployment_id="20260101T000000Z_missing",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_and_staged_deployments_when_switching_ids_then_persisted_state_replaces(
    test_case: DeploymentBrowserE2ETestCase,
    running_deployment_browser_server: tuple[str, str, str, str, Path],
    e2e_clickhouse_client: Client,
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, active_id, staged_id, database, _log_path = running_deployment_browser_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/deployments"
    ) as inventory_info:
        document_response: Response | None = page.goto(
            f"{base_url}/deployments", wait_until="domcontentloaded", timeout=30_000
        )
    assert document_response is not None
    assert document_response.status == 200
    inventory_payload: dict[str, object] = inventory_info.value.json()
    deployments: list[dict[str, object]] = cast(
        list[dict[str, object]], inventory_payload["deployments"]
    )
    deployment_by_id: dict[str, dict[str, object]] = {
        str(deployment["deploymentId"]): deployment for deployment in deployments
    }
    assert deployment_by_id[active_id]["state"] == "active"
    assert deployment_by_id[staged_id]["state"] == "staged"
    assert deployment_by_id[active_id]["activeBindingNames"]
    assert deployment_by_id[staged_id]["activeBindingNames"] == []
    expect(page.get_by_role("link", name=active_id, exact=True)).to_be_visible()
    staged_link: Locator = page.get_by_role("link", name=staged_id, exact=True)
    expect(staged_link).to_be_visible()
    active_cells: Locator = page.get_by_test_id("deployment-table-active").locator("td")
    staged_cells: Locator = page.get_by_test_id("deployment-table-staged").locator("td")
    active_column_x: tuple[float, ...] = tuple(
        cast(dict[str, float], active_cells.nth(index).bounding_box())["x"] for index in range(1, 5)
    )
    staged_column_x: tuple[float, ...] = tuple(
        cast(dict[str, float], staged_cells.nth(index).bounding_box())["x"] for index in range(1, 5)
    )
    assert active_column_x == pytest.approx(staged_column_x, abs=1)

    with page.expect_response(
        lambda response: urlparse(response.url).path == f"/api/deployments/{staged_id}"
    ) as staged_info:
        staged_link.click()
    staged_detail: dict[str, object] = staged_info.value.json()
    assert staged_detail["state"] == "staged"
    staged_models: list[dict[str, object]] = cast(list[dict[str, object]], staged_detail["models"])
    staged_model_by_name: dict[str, dict[str, object]] = {
        str(model["logicalName"]): model for model in staged_models
    }
    changed_model: dict[str, object] = staged_model_by_name[test_case.expected_changed_model]
    assert changed_model["liveDeploymentId"] == active_id
    assert staged_id in str(changed_model["stagedRelation"])
    assert active_id in str(changed_model["liveRelation"])
    preview: dict[str, object] = cast(dict[str, object], staged_detail["promotionPreview"])
    replacements: list[dict[str, object]] = cast(list[dict[str, object]], preview["replacements"])
    replacement_by_name: dict[str, dict[str, object]] = {
        str(item["logicalName"]): item for item in replacements
    }
    replacement: dict[str, object] = replacement_by_name[test_case.expected_changed_model]
    assert active_id in str(replacement["fromPhysicalName"])
    assert staged_id in str(replacement["toPhysicalName"])
    expect(page.get_by_role("button", name="Promote", exact=True)).to_be_visible()
    action_table: Locator = page.get_by_role("table").filter(
        has=page.get_by_role("columnheader", name="Action", exact=True)
    )
    changed_row: Locator = action_table.get_by_role("row").filter(
        has=page.get_by_role("cell", name=test_case.expected_changed_model, exact=True)
    )
    expect(changed_row).to_contain_text("replace")
    expect(changed_row).to_contain_text(active_id)
    expect(changed_row).to_contain_text(staged_id)

    with page.expect_response(
        lambda response: urlparse(response.url).path == f"/api/deployments/{staged_id}/diff"
    ) as diff_info:
        page.get_by_role("button", name="Diff", exact=True).click()
    diff_payload: dict[str, object] = diff_info.value.json()
    assert diff_payload["fromEndpoint"] == "active"
    assert diff_payload["toEndpoint"] == staged_id
    diff_relations: list[dict[str, object]] = cast(
        list[dict[str, object]], diff_payload["relations"]
    )
    diff_by_name: dict[str, dict[str, object]] = {
        str(relation["logicalName"]): relation for relation in diff_relations
    }
    assert test_case.expected_changed_model in diff_by_name
    persisted_queries: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT deployment_id, canonical_query FROM {database}."
            "_streambuild_virtual_object_state WHERE state_kind = 'deployment' "
            f"AND logical_model_name = '{test_case.expected_changed_model}' "
            "AND canonical_query IS NOT NULL ORDER BY deployment_id"
        ).result_rows
    )
    query_by_deployment: dict[str, str] = {
        str(deployment_id): str(query) for deployment_id, query in persisted_queries
    }
    assert query_by_deployment[active_id] != query_by_deployment[staged_id]
    assert "concat(customers.customer_name, '!')" not in query_by_deployment[active_id]
    assert "concat(customers.customer_name, '!')" in query_by_deployment[staged_id]
    active_values: tuple[str, ...] = tuple(
        str(row[0])
        for row in e2e_clickhouse_client.query(
            f"SELECT customer_name FROM {database}.`{changed_model['liveRelation']}` "
            "ORDER BY order_id"
        ).result_rows
    )
    staged_values: tuple[str, ...] = tuple(
        str(row[0])
        for row in e2e_clickhouse_client.query(
            f"SELECT customer_name FROM {database}.`{changed_model['stagedRelation']}` "
            "ORDER BY order_id"
        ).result_rows
    )
    assert active_values[0] == test_case.expected_active_value
    assert staged_values[0] == test_case.expected_staged_value
    expect(page.get_by_role("button", name="Diff", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(
        page.get_by_role("table").filter(
            has=page.get_by_role("columnheader", name="Status", exact=True)
        )
    ).to_be_visible()

    live_link: Locator = page.get_by_role(
        "link", name=f"Open live deployment {active_id}", exact=True
    ).first
    with page.expect_response(
        lambda response: urlparse(response.url).path == f"/api/deployments/{active_id}"
    ) as active_info:
        live_link.click()
    active_detail: dict[str, object] = active_info.value.json()
    assert active_detail["state"] == "active"
    assert active_detail["activeBindingNames"]
    expect(page).to_have_url(f"{base_url}/deployments/{active_id}")
    expect(page.get_by_role("button", name="Graph", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.get_by_role("columnheader", name="Status", exact=True)).to_have_count(0)
    expect(page.get_by_text(staged_id, exact=True)).to_have_count(0)
    assert all(message.type != "error" for message in console_messages)

    with page.expect_response(
        lambda response: (
            urlparse(response.url).path == f"/api/deployments/{test_case.missing_deployment_id}"
            and response.status == 404
        )
    ):
        page.goto(
            f"{base_url}/deployments/{test_case.missing_deployment_id}",
            wait_until="domcontentloaded",
        )
    expect(
        page.get_by_role("heading", name=test_case.missing_deployment_id, exact=True)
    ).to_be_visible()
    expect(
        page.get_by_text(
            f"deployment '{test_case.missing_deployment_id}' was not found", exact=True
        )
    ).to_be_visible()
    expect(page.get_by_role("button", name="Promote", exact=True)).to_have_count(0)
    expect(page.get_by_role("columnheader", name="Action", exact=True)).to_have_count(0)

    assert all(
        message.type != "error" or "404 (Not Found)" in message.text for message in console_messages
    )
    assert page_errors == []
    assert {(urlparse(request.url).path, request.failure) for request in failed_requests} <= {
        ("/api/definitions", "net::ERR_ABORTED")
    }
    assert all(
        response.status < 400
        or (
            response.status == 404
            and urlparse(response.url).path == f"/api/deployments/{test_case.missing_deployment_id}"
        )
        for response in responses
    )
