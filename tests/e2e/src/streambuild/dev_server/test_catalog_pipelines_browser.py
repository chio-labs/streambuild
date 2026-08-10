from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import pytest
from clickhouse_connect.driver.client import Client
from playwright.sync_api import ConsoleMessage, Error, Locator, Page, Request, Response, expect

from tests.e2e.src.streambuild.dev_server._test_types import CatalogPipelineBrowserE2ETestCase

PARENT_AUTHORED_SQL: str = """MODEL (
  engine "MergeTree()",
  order_by ["order_id"]
);

SELECT
  order_id::String AS order_id,
  _replay_timestamp::DateTime64(3) AS _replay_timestamp
FROM __ref("moving_events")
"""


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        CatalogPipelineBrowserE2ETestCase(
            description="pipeline dependencies and catalog SQL remain exact across routes",
            pipeline_name="moving_events",
            parent_model="moving_orders",
            child_model="derived_moving_orders",
            expected_relation="tbl__moving_orders",
            expected_child_relation="tbl__derived_moving_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_pipeline_when_navigating_catalog_then_identity_and_sql_replace_exactly(
    test_case: CatalogPipelineBrowserE2ETestCase,
    running_catalog_pipeline_browser_server: tuple[str, dict[str, object], str, Path],
    e2e_clickhouse_client: Client,
    browser_diagnostics: tuple[list[ConsoleMessage], list[Error], list[Request], list[Response]],
    page: Page,
) -> None:
    base_url, state_payload, database, _log_path = running_catalog_pipeline_browser_server
    console_messages, page_errors, failed_requests, responses = browser_diagnostics
    with page.expect_response(
        lambda response: urlparse(response.url).path == "/api/definitions"
    ) as definitions_info:
        document_response: Response | None = page.goto(
            f"{base_url}/pipelines/{test_case.pipeline_name}",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
    assert document_response is not None
    assert document_response.status == 200
    definitions: dict[str, object] = definitions_info.value.json()
    pipelines: list[dict[str, object]] = cast(list[dict[str, object]], definitions["pipelines"])
    pipeline_by_name: dict[str, dict[str, object]] = {str(item["name"]): item for item in pipelines}
    pipeline: dict[str, object] = pipeline_by_name[test_case.pipeline_name]
    assert pipeline["mode"] == "direct"
    assert pipeline["sourceName"] == test_case.pipeline_name
    assert pipeline["boundaryMode"] == "timestamp"
    assert pipeline["directory"] == f"pipelines/{test_case.pipeline_name}"
    assert set(cast(list[str], pipeline["models"])) == {
        test_case.parent_model,
        test_case.child_model,
    }

    models: list[dict[str, object]] = cast(list[dict[str, object]], definitions["models"])
    model_by_name: dict[str, dict[str, object]] = {str(item["name"]): item for item in models}
    parent: dict[str, object] = model_by_name[test_case.parent_model]
    child: dict[str, object] = model_by_name[test_case.child_model]
    assert parent["relationName"] == test_case.expected_relation
    assert parent["drivingInput"] == test_case.pipeline_name
    assert child["relationName"] == test_case.expected_child_relation
    assert child["mvRelationName"] == "mv__derived_moving_orders"
    assert child["drivingInput"] == test_case.parent_model
    assert child["refs"] == [
        {"name": test_case.parent_model, "type": "driving_input", "isSource": False}
    ]
    state_models: dict[str, dict[str, object]] = cast(
        dict[str, dict[str, object]], state_payload["models"]
    )
    assert state_models[test_case.parent_model]["relationName"] == test_case.expected_relation
    assert state_models[test_case.child_model]["relationName"] == test_case.expected_child_relation

    tree: Locator = page.get_by_test_id("stream-tree")
    expect(tree).to_be_visible()
    tree_item_locator: Locator = tree.locator("[data-node-name]")
    expect(tree_item_locator).to_have_count(3)
    tree_items: list[Locator] = tree_item_locator.all()
    assert [item.get_attribute("data-node-name") for item in tree_items] == [
        test_case.pipeline_name,
        test_case.parent_model,
        test_case.child_model,
    ]
    expect(page.get_by_role("button", name="Tree", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    page.get_by_role("button", name="Graph", exact=True).click()
    expect(page).to_have_url(f"{base_url}/pipelines/{test_case.pipeline_name}?view=graph")
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_role("button", name="Graph", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )

    page.goto(f"{base_url}/catalog", wait_until="domcontentloaded")
    parent_link: Locator = page.get_by_role("link", name=test_case.parent_model, exact=True)
    parent_row: Locator = page.get_by_role("row").filter(has=parent_link)
    expect(parent_row).to_contain_text(test_case.expected_relation)
    parent_link.click()
    expect(page).to_have_url(f"{base_url}/catalog/{test_case.parent_model}")
    parent_sql: dict[str, object] = cast(dict[str, object], parent["sql"])
    assert parent_sql["authored"] == PARENT_AUTHORED_SQL
    expect(page.locator('[data-sql-artifact="Model"]')).to_have_text(PARENT_AUTHORED_SQL)
    page.get_by_role("button", name="Compiled", exact=True).click()
    parent_compiled: str = cast(str, parent_sql["compiled"])
    expect(page.locator('[data-sql-artifact="Compiled"]')).to_have_text(parent_compiled)
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    page.get_by_role("button", name="Copy Compiled SQL", exact=True).click()
    assert page.evaluate("navigator.clipboard.readText()") == parent_compiled

    page.get_by_role("link", name=test_case.child_model, exact=True).click()
    expect(page).to_have_url(f"{base_url}/catalog/{test_case.child_model}")
    expect(
        page.get_by_text(f"pipelines/{test_case.pipeline_name}/{test_case.child_model}.sql")
    ).to_be_visible()
    child_sql: dict[str, object] = cast(dict[str, object], child["sql"])
    child_compiled: str = cast(str, child_sql["compiled"])
    compiled_panel: Locator = page.locator('[data-sql-artifact="Compiled"]')
    expect(compiled_panel).to_have_text(child_compiled)
    expect(compiled_panel).to_contain_text(f"FROM {test_case.expected_relation}")
    expect(compiled_panel).not_to_contain_text("browser_moving_events")
    expect(page.get_by_text(test_case.expected_child_relation, exact=True)).to_be_visible()
    page.get_by_role("button", name="Copy Compiled SQL", exact=True).click()
    assert page.evaluate("navigator.clipboard.readText()") == child_compiled
    materialized_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in e2e_clickhouse_client.query(
            f"SELECT order_id FROM {database}.{test_case.expected_child_relation}"
        ).result_rows
    )
    assert materialized_rows == (("catalog-42",),)
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=test_case.child_model, exact=True)).to_be_visible()
    page.get_by_role("button", name="Compiled", exact=True).click()
    expect(page.locator('[data-sql-artifact="Compiled"]')).to_have_text(child_compiled)

    assert all(message.type != "error" for message in console_messages)
    assert page_errors == []
    assert failed_requests == []
    assert all(response.status < 400 for response in responses)
