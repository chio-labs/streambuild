import pytest

from streambuild.clickhouse.inspect.helpers.deployments import inspect_root_deployment_state
from streambuild.clickhouse.inspect.models import (
    InspectedActiveTableBinding,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
    RootDeploymentInspection,
)
from streambuild.compiler.shared.models import ObjectKey
from tests.unit.src.streambuild.clickhouse.inspect._test_types import (
    InspectRootDeploymentStateTestCase,
)

TEST_CASES: list[InspectRootDeploymentStateTestCase] = [
    InspectRootDeploymentStateTestCase(
        description="classifies active view binding as active deployment",
        active_bindings=(("tbl__orders_enriched", "tbl__orders_enriched__dep_a"),),
        physical_candidates=(("tbl__orders_enriched", "tbl__orders_enriched__dep_a"),),
        expected_state_kind="active_view_present",
        expected_active_deployment_id="dep_a",
    ),
    InspectRootDeploymentStateTestCase(
        description="classifies no view and no candidates as greenfield",
        active_bindings=(),
        physical_candidates=(),
        expected_state_kind="greenfield",
        expected_active_deployment_id=None,
    ),
    InspectRootDeploymentStateTestCase(
        description="classifies no view with candidates as logical view missing",
        active_bindings=(),
        physical_candidates=(
            ("tbl__orders_enriched", "tbl__orders_enriched__dep_a"),
            ("tbl__orders_enriched", "tbl__orders_enriched__dep_b"),
        ),
        expected_state_kind="logical_view_missing",
        expected_active_deployment_id=None,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_inspected_root_state_when_classifying_then_it_returns_expected_state_kind(
    test_case: InspectRootDeploymentStateTestCase,
) -> None:
    inspected_state: InspectedManagedTableState = InspectedManagedTableState(
        active_bindings=tuple(
            InspectedActiveTableBinding(
                database="analytics",
                logical_name=logical_name,
                physical_name=physical_name,
            )
            for logical_name, physical_name in test_case.active_bindings
        ),
        physical_candidates=tuple(
            InspectedPhysicalTableCandidate(
                database="analytics",
                logical_name=logical_name,
                physical_name=physical_name,
            )
            for logical_name, physical_name in test_case.physical_candidates
        ),
    )

    result: RootDeploymentInspection = inspect_root_deployment_state(
        inspected_state=inspected_state,
        root_key=ObjectKey(database="analytics", object_type="table", name="tbl__orders_enriched"),
    )

    assert result.state_kind == test_case.expected_state_kind
    assert result.active_deployment_id == test_case.expected_active_deployment_id
