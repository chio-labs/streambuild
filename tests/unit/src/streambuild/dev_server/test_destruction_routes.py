from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.auth.classes.control_store import ControlStore
from streambuild.executor.destruction.exceptions import (
    DestructionDependencyError,
    DestructionResourceError,
)
from streambuild.executor.destruction.models import DestructionPlan
from tests.unit.src.streambuild.dev_server._test_types import (
    DestructionActorBindingRouteTestCase,
    DestructionAuthorizationRouteTestCase,
    DestructionClosureAuthorizationRouteTestCase,
    DestructionResetRouteTestCase,
    DestructionResourceConflictRouteTestCase,
    DestructionRestartRouteTestCase,
    DestructionReviewGateRouteTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    build_assigned_proxy_operations_client,
    build_pipeline_destruction_route_plan,
    build_proxy_test_client,
    build_target_reset_route_plan,
    proxy_proof_headers,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionAuthorizationRouteTestCase(
            description="pipeline destroy scope permits only its assigned actor",
            expected_denied_status=403,
            expected_reason="system_admin_required",
            expected_allowed_status=200,
            expected_plan_id="plan-1",
            expected_planner_call_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_destroy_permission_when_planning_then_http_boundary_enforces_scope(
    tmp_path: Path,
    test_case: DestructionAuthorizationRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    with patch(
        "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
        return_value=build_pipeline_destruction_route_plan(),
    ) as planner:
        denied: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=proxy_proof_headers(username="bob"),
        )
        allowed: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=proxy_proof_headers(username="alice"),
        )

    assert denied.status_code == test_case.expected_denied_status
    assert denied.json()["detail"]["reason"] == test_case.expected_reason
    assert allowed.status_code == test_case.expected_allowed_status
    assert allowed.json()["planId"] == test_case.expected_plan_id
    assert planner.call_count == test_case.expected_planner_call_count
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionResourceConflictRouteTestCase(
            description="recorded resource conflict returns a structured response",
            conflict_message="recorded virtual resource is in another database",
            expected_status=409,
            expected_reason="resource_conflict",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_resource_conflict_when_planning_then_api_returns_actionable_conflict(
    tmp_path: Path,
    test_case: DestructionResourceConflictRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    with patch(
        "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
        side_effect=DestructionResourceError(test_case.conflict_message),
    ):
        response: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=proxy_proof_headers(username="alice"),
        )

    assert response.status_code == test_case.expected_status
    assert response.json()["detail"] == {
        "message": test_case.conflict_message,
        "reason": test_case.expected_reason,
    }
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionClosureAuthorizationRouteTestCase(
            description="suggested dependent closure is reauthorized before disclosure",
            dependent_pipeline="reporting",
            expected_status=403,
            expected_permission="pipeline.destroy",
            expected_authorization_call_count=2,
            expected_planner_call_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unauthorized_dependant_when_planning_then_suggested_closure_is_hidden(
    tmp_path: Path,
    test_case: DestructionClosureAuthorizationRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    blocked_plan: DestructionPlan = replace(
        build_pipeline_destruction_route_plan(),
        included_dependent_pipeline_names=(test_case.dependent_pipeline,),
        affected_pipeline_names=("order_events", test_case.dependent_pipeline),
    )
    with (
        patch(
            "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
            side_effect=(
                DestructionDependencyError((test_case.dependent_pipeline,)),
                blocked_plan,
            ),
        ) as planner,
        patch(
            "streambuild.dev_server._helpers.server.destruction_routes."
            "require_destruction_authorization",
            side_effect=(
                None,
                HTTPException(
                    status_code=test_case.expected_status,
                    detail={"permission": test_case.expected_permission},
                ),
            ),
        ) as authorization,
    ):
        response: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=proxy_proof_headers(username="alice"),
        )

    assert response.status_code == test_case.expected_status
    assert response.json()["detail"]["permission"] == test_case.expected_permission
    assert authorization.call_count == test_case.expected_authorization_call_count
    assert planner.call_count == test_case.expected_planner_call_count
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionResetRouteTestCase(
            description="target reset scope permits planning",
            expected_status=200,
            expected_managed_sources_included=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_reset_permission_when_planning_then_reset_scope_is_allowed(
    tmp_path: Path,
    test_case: DestructionResetRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    with patch(
        "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
        return_value=build_target_reset_route_plan(),
    ):
        response: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "reset_target", "pipelineNames": []},
            headers=proxy_proof_headers(username="alice"),
        )

    assert response.status_code == test_case.expected_status
    assert response.json()["managedSourcesIncluded"] is test_case.expected_managed_sources_included
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionReviewGateRouteTestCase(
            description="execution cannot bypass server review",
            expected_status=409,
            expected_detail_fragment="has not been reviewed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unreviewed_plan_when_executing_then_server_review_gate_blocks(
    tmp_path: Path,
    test_case: DestructionReviewGateRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    headers: dict[str, str] = proxy_proof_headers(username="alice")
    with patch(
        "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
        return_value=build_pipeline_destruction_route_plan(),
    ):
        created: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=headers,
        )
        response: Response = client.post(
            f"/api/destruction/plans/{created.json()['planId']}/execute",
            json={"responses": ["order_events"]},
            headers=headers,
        )

    assert response.status_code == test_case.expected_status
    assert test_case.expected_detail_fragment in response.json()["detail"]
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionActorBindingRouteTestCase(
            description="another actor cannot discover a frozen plan",
            expected_status=404,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_another_actor_plan_when_reviewing_then_creator_binding_hides_plan(
    tmp_path: Path,
    test_case: DestructionActorBindingRouteTestCase,
) -> None:
    client: TestClient
    store: ControlStore
    client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    with patch(
        "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
        return_value=build_pipeline_destruction_route_plan(),
    ):
        created: Response = client.post(
            "/api/destruction/plans",
            json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
            headers=proxy_proof_headers(username="alice"),
        )
        response: Response = client.post(
            f"/api/destruction/plans/{created.json()['planId']}/review",
            headers=proxy_proof_headers(username="bob"),
        )

    assert response.status_code == test_case.expected_status
    store.close()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionRestartRouteTestCase(
            description="reviewed plan survives dev server reconstruction",
            expected_plan_id="plan-1",
            expected_reviewed_status=200,
            expected_reloaded_status=200,
            expected_mismatched_review_status=409,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reviewed_plan_when_dev_app_is_reconstructed_then_http_plan_survives(
    tmp_path: Path,
    test_case: DestructionRestartRouteTestCase,
) -> None:
    first_client: TestClient
    store: ControlStore
    first_client, store = build_assigned_proxy_operations_client(project_dir=tmp_path)
    headers: dict[str, str] = proxy_proof_headers(username="alice")
    with first_client:
        with patch(
            "streambuild.dev_server._helpers.server.destruction_routes.plan_destruction",
            return_value=build_pipeline_destruction_route_plan(),
        ):
            created: Response = first_client.post(
                "/api/destruction/plans",
                json={"operation": "destroy_pipelines", "pipelineNames": ["order_events"]},
                headers=headers,
            )
            reviewed: Response = first_client.post(
                f"/api/destruction/plans/{created.json()['planId']}/review",
                headers=headers,
            )

    second_client: TestClient = build_proxy_test_client(project_dir=tmp_path, store=store)
    with second_client:
        reloaded: Response = second_client.get(
            f"/api/destruction/plans/{test_case.expected_plan_id}",
            headers=headers,
        )
        mismatched_review: Response = second_client.post(
            f"/api/destruction/plans/{test_case.expected_plan_id}/review",
            headers=headers,
        )

    assert reviewed.status_code == test_case.expected_reviewed_status
    assert reloaded.status_code == test_case.expected_reloaded_status
    assert reloaded.json()["planId"] == test_case.expected_plan_id
    assert mismatched_review.status_code == test_case.expected_mismatched_review_status
    store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
