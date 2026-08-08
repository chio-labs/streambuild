from typing import cast

import pytest

from streambuild.dev_server._helpers.payloads.deployments_payload import (
    build_deployment_detail_payload,
    build_deployments_payload,
)
from tests.unit.src.streambuild.dev_server._test_types import (
    DeploymentDetailMissingTestCase,
    DeploymentDetailTestCase,
    DeploymentsPayloadTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    DEPLOYMENT_ACTIVE_ID,
    DEPLOYMENT_STAGED_ID,
    build_fake_deployment_connection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeploymentsPayloadTestCase(
            description="newest deployment first with landing views excluded from model counts",
            expected_deployment_ids=(DEPLOYMENT_STAGED_ID, DEPLOYMENT_ACTIVE_ID),
            expected_states=("staged", "active"),
            expected_model_counts=(3, 2),
            expected_rows=(1267, 1050),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_staged_and_active_deployments_when_building_payload_then_totals_are_exact(
    test_case: DeploymentsPayloadTestCase,
) -> None:
    payload: dict[str, object] = build_deployments_payload(
        connection=build_fake_deployment_connection(),
        database="analytics",
        metadata_database="analytics",
    )

    deployments: list[dict[str, object]] = cast(list[dict[str, object]], payload["deployments"])
    assert tuple(str(item["deploymentId"]) for item in deployments) == (
        test_case.expected_deployment_ids
    )
    assert tuple(str(item["state"]) for item in deployments) == test_case.expected_states
    assert tuple(int(cast(int, item["modelCount"])) for item in deployments) == (
        test_case.expected_model_counts
    )
    assert tuple(int(cast(int, item["rows"])) for item in deployments) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        DeploymentDetailTestCase(
            description="staged detail pairs each model with its live counterpart",
            deployment_id=DEPLOYMENT_STAGED_ID,
            expected_state="staged",
            expected_logical_names=("tbl__orders", "tbl__refunds", "tbl__revenue"),
            expected_staged_rows=(1200, 7, 60),
            expected_live_rows=(1000, None, 50),
            expected_new_flags=(False, True, False),
            expected_orphan_relations=2,
        ),
        DeploymentDetailTestCase(
            description="active detail reports no orphaned relations",
            deployment_id=DEPLOYMENT_ACTIVE_ID,
            expected_state="active",
            expected_logical_names=("tbl__orders", "tbl__revenue"),
            expected_staged_rows=(1000, 50),
            expected_live_rows=(1000, 50),
            expected_new_flags=(False, False),
            expected_orphan_relations=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deployment_when_building_detail_then_live_comparison_is_exact(
    test_case: DeploymentDetailTestCase,
) -> None:
    payload: dict[str, object] | None = build_deployment_detail_payload(
        connection=build_fake_deployment_connection(),
        database="analytics",
        metadata_database="analytics",
        deployment_id=test_case.deployment_id,
    )

    resolved: dict[str, object] = cast(dict[str, object], payload)
    assert str(resolved["state"]) == test_case.expected_state
    models: list[dict[str, object]] = cast(list[dict[str, object]], resolved["models"])
    assert tuple(str(model["logicalName"]) for model in models) == (
        test_case.expected_logical_names
    )
    assert tuple(int(cast(int, model["stagedRows"])) for model in models) == (
        test_case.expected_staged_rows
    )
    assert tuple(cast(int | None, model["liveRows"]) for model in models) == (
        test_case.expected_live_rows
    )
    assert tuple(bool(model["isNew"]) for model in models) == test_case.expected_new_flags
    orphan: dict[str, object] = cast(dict[str, object], resolved["wouldOrphan"])
    assert int(cast(int, orphan["relationCount"])) == test_case.expected_orphan_relations


@pytest.mark.parametrize(
    "test_case",
    [
        DeploymentDetailMissingTestCase(
            description="unknown deployment id yields no payload",
            deployment_id="20260101T000000Z_missing",
            expected_payload=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_deployment_when_building_detail_then_no_payload_is_returned(
    test_case: DeploymentDetailMissingTestCase,
) -> None:
    payload: dict[str, object] | None = build_deployment_detail_payload(
        connection=build_fake_deployment_connection(),
        database="analytics",
        metadata_database="analytics",
        deployment_id=test_case.deployment_id,
    )

    assert payload == test_case.expected_payload


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
