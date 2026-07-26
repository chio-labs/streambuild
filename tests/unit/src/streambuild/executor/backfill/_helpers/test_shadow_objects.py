from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.executor.backfill._helpers.shadow_objects import create_shadow_objects
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_single_transform_desired_state,
)
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    CreateShadowObjectsOrderingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CreateShadowObjectsOrderingTestCase(
            description=(
                "creates referenced shadow tables before dependent shadow materialized views"
            ),
            expected_preceding_fragment="CREATE TABLE analytics.tbl__region_lookup__dep_ref",
            expected_following_fragment=(
                "CREATE MATERIALIZED VIEW analytics.mv__orders_enriched__dep_ref"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reference_ref_when_creating_shadow_objects_then_it_creates_dependency_tables_first(
    test_case: CreateShadowObjectsOrderingTestCase,
) -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.commands: list[str] = []

        def query(self, _statement: str) -> object:
            class QueryResult:
                rows: tuple[tuple[object, ...], ...] = ()

            return QueryResult()

        def command(self, statement: str) -> None:
            self.commands.append(statement)

    desired_state: DesiredState = build_single_transform_desired_state(
        query=(
            "SELECT CAST(o.order_id AS UInt64) AS order_id, "
            "CAST(o._replay_partition AS UInt64) AS _replay_partition, "
            "CAST(o._replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders") AS o LEFT JOIN '
            '__ref("region_lookup", ref_type="reference") AS r ON o.order_id = r.region_id'
        ),
        order_by=("order_id", "_replay_partition", "_replay_offset"),
        supporting_transforms=(
            (
                "region_lookup",
                "SELECT CAST(order_id AS UInt64) AS region_id, "
                "CAST(_replay_partition AS UInt64) AS _replay_partition, "
                "CAST(_replay_offset AS UInt64) AS _replay_offset "
                'FROM __ref("orders")',
                ("region_id",),
            ),
        ),
    )
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=ActualState(objects=()),
        default_database="analytics",
        deployment_id="dep_ref",
    )
    client: RecordingClient = RecordingClient()

    create_shadow_objects(
        client=cast(AdapterConnection, client),
        deployment_plan=deployment_plan,
        desired_state=desired_state,
        default_database="analytics",
    )

    rendered_commands: str = "\n".join(client.commands)
    preceding_index: int = rendered_commands.index(test_case.expected_preceding_fragment)
    following_index: int = rendered_commands.index(test_case.expected_following_fragment)

    assert preceding_index < following_index
