import re
from pathlib import Path
from typing import cast

import pytest
from playwright.sync_api import FloatRect, Locator, Page, Route, expect

from tests.e2e.src.streambuild.dev_server._test_types import (
    DestructionBrowserE2ETestCase,
)


class DestructionRouteRecorder:
    def __init__(self, *, plan_payload: dict[str, object], invocation_id: str) -> None:
        self.plan_payload: dict[str, object] = plan_payload
        self.invocation_id: str = invocation_id
        self.request_bodies: list[dict[str, object]] = []
        self.reviewed_at: str | None = None
        self.read_count: int = 0

    def fulfill_plan(self, route: Route) -> None:
        self.request_bodies.append(cast(dict[str, object], route.request.post_data_json))
        route.fulfill(json=self.plan_payload)

    def fulfill_review(self, route: Route) -> None:
        self.request_bodies.append({})
        self.reviewed_at = "2026-08-24T12:01:00+00:00"
        route.fulfill(json={**self.plan_payload, "reviewedAt": self.reviewed_at})

    def fulfill_read(self, route: Route) -> None:
        self.read_count += 1
        route.fulfill(json={**self.plan_payload, "reviewedAt": self.reviewed_at})

    def fulfill_execution(self, route: Route) -> None:
        self.request_bodies.append(cast(dict[str, object], route.request.post_data_json))
        route.fulfill(status=202, json={"invocationId": self.invocation_id, "status": "starting"})


@pytest.mark.e2e
@pytest.mark.browser
@pytest.mark.parametrize(
    "test_case",
    [
        DestructionBrowserE2ETestCase(
            description="typed destruction gates preserve exact request boundaries",
            pipeline_name="pl__moving_events",
            expected_model_name="moving_orders",
            expected_relation_name="tbl__moving_orders",
            expected_invocation_id="destroy-run-1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_pipeline_when_confirming_destruction_then_both_gates_are_required(
    test_case: DestructionBrowserE2ETestCase,
    running_catalog_pipeline_browser_server: tuple[str, dict[str, object], str, Path],
    page: Page,
) -> None:
    base_url: str = running_catalog_pipeline_browser_server[0]
    plan_payload: dict[str, object] = {
        "planId": "plan-1",
        "planFingerprint": "a" * 64,
        "operation": "destroy_pipelines",
        "target": "test",
        "database": "analytics",
        "selectedPipelines": [test_case.pipeline_name],
        "includedDependentPipelines": [],
        "affectedPipelines": [test_case.pipeline_name],
        "requiredDependentPipelines": [],
        "blocked": False,
        "models": [test_case.expected_model_name, *(f"model_{index:03d}" for index in range(60))],
        "resources": [
            {
                "name": test_case.expected_relation_name,
                "kind": "table",
                "logicalName": test_case.expected_model_name,
                "pipelineName": test_case.pipeline_name,
                "exists": True,
                "bytes": 4096,
                "activeParts": 2,
            },
            *(
                {
                    "name": f"tbl__resource_{index:03d}",
                    "kind": "table",
                    "logicalName": f"resource_{index:03d}",
                    "pipelineName": test_case.pipeline_name,
                    "exists": True,
                    "bytes": 0,
                    "activeParts": 0,
                }
                for index in range(1, 31)
            ),
        ],
        "managedSourcesIncluded": False,
        "retainedReplayDataIncluded": False,
        "estimatedBytes": 4096,
        "challengeValues": [test_case.pipeline_name],
        "expiresAt": "2099-08-24T12:15:00+00:00",
        "reviewedAt": None,
    }
    routes: DestructionRouteRecorder = DestructionRouteRecorder(
        plan_payload=plan_payload,
        invocation_id=test_case.expected_invocation_id,
    )

    page.route("**/api/destruction/plans", routes.fulfill_plan)
    page.route("**/api/destruction/plans/plan-1", routes.fulfill_read)
    page.route("**/api/destruction/plans/plan-1/review", routes.fulfill_review)
    page.route("**/api/destruction/plans/plan-1/execute", routes.fulfill_execution)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(f"{base_url}/pipelines", wait_until="domcontentloaded")

    page.get_by_role("button", name=re.compile(r"^Virtual")).click()
    expect(page.get_by_text("No pipelines match this mode", exact=True)).to_be_visible()
    expect(page.get_by_label(f"Select {test_case.pipeline_name} for destruction")).to_have_count(0)
    page.get_by_role("button", name=re.compile(r"^Direct")).click()
    expect(page.get_by_label(f"Select {test_case.pipeline_name} for destruction")).to_be_visible()

    page.get_by_label(f"Select {test_case.pipeline_name} for destruction").click()
    page.get_by_role("button", name="Destroy (1)").click()
    expect(page).to_have_url(f"{base_url}/destruction/plans/plan-1")
    expect(page.get_by_text("Frozen pipeline closure")).to_be_visible()
    expect(page.get_by_text(test_case.expected_relation_name, exact=True)).to_be_visible()
    content_box: FloatRect | None = page.get_by_test_id("destruction-plan-content").bounding_box()
    assert content_box is not None
    assert content_box["width"] > 1600
    expect(page.get_by_test_id("destruction-resource-row")).to_have_count(25)
    expect(page.get_by_text("Showing 1-25 of 31 frozen resources", exact=True)).to_be_visible()
    page.get_by_role("button", name="Next resource page").click()
    expect(page.get_by_test_id("destruction-resource-row")).to_have_count(6)
    expect(page.get_by_text("tbl__resource_025", exact=True)).to_be_visible()
    page.get_by_role("button", name="Show all 61 models").click()
    expect(page.get_by_text("model_059", exact=True)).to_be_visible()
    page.get_by_role("button", name="Show fewer models").click()
    expect(page.get_by_text("model_059", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Review frozen plan")).to_be_enabled()
    page.get_by_role("button", name="Review frozen plan").click()

    challenge: Locator = page.get_by_label(f"Challenge 1: {test_case.pipeline_name}")
    execute: Locator = page.get_by_role("button", name="Destroy pipelines", exact=True)
    challenge.fill(f"{test_case.pipeline_name} ")
    expect(execute).to_be_disabled()
    challenge.fill(test_case.pipeline_name)
    expect(execute).to_be_enabled()
    page.reload(wait_until="domcontentloaded")

    challenge = page.get_by_label(f"Challenge 1: {test_case.pipeline_name}")
    execute = page.get_by_role("button", name="Destroy pipelines", exact=True)
    expect(challenge).to_have_value("")
    expect(execute).to_be_disabled()
    challenge.fill(test_case.pipeline_name)
    execute.click()

    expect(page).to_have_url(f"{base_url}/runs/{test_case.expected_invocation_id}?live=1")
    assert routes.request_bodies == [
        {
            "operation": "destroy_pipelines",
            "pipelineNames": [test_case.pipeline_name],
            "includedDependentPipelineNames": [],
        },
        {},
        {"responses": [test_case.pipeline_name]},
    ]
    assert routes.read_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
