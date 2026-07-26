from dataclasses import replace

import pytest

import streambuild.executor.backfill._helpers.bootstrap as bootstrap_module
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.constants import REBUILD_EXECUTION_MODE_SEEDED_BOUNDED
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import ActualState, DeploymentPlan, RebuildSubtree
from streambuild.executor.backfill.models import BackfillBootstrapRequest
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import build_example_desired_state
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    HistoryPrefixCapabilityTestCase,
    ManagedSourceCapabilityTestCase,
    ReplayBoundaryCapabilityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ManagedSourceCapabilityTestCase(
            description="unsupported managed source fails before warehouse interaction",
            expected_error_message=(
                "Adapter 'clickhouse' does not support managed source kind 'kafka'"
            ),
            expected_warehouse_interaction_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_managed_source_when_bootstrapping_then_it_fails_before_writes(
    test_case: ManagedSourceCapabilityTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        managed_source_kinds=frozenset()
    )
    request: BackfillBootstrapRequest = BackfillBootstrapRequest(
        desired_state=build_example_desired_state(),
        default_database="analytics",
        metadata_database="metadata",
        replay_lineage_mode="offsets",
    )

    with pytest.raises(AdapterCapabilityError) as error:
        bootstrap_module.execute_backfill_bootstrap(request=request, client=connection)

    interaction_count: int = len(connection.statements) + len(connection.catalog_databases)
    assert str(error.value) == test_case.expected_error_message
    assert interaction_count == test_case.expected_warehouse_interaction_count


@pytest.mark.parametrize(
    "test_case",
    [
        ReplayBoundaryCapabilityTestCase(
            description="unsupported replay boundary fails before warehouse interaction",
            expected_error_message=(
                "Adapter 'clickhouse' does not support replay boundary mode 'offsets'"
            ),
            expected_warehouse_interaction_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_replay_mode_when_bootstrapping_then_it_fails_before_writes(
    test_case: ReplayBoundaryCapabilityTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        replay_boundary_modes=frozenset(
            {
                AdapterReplayBoundaryMode.TIMESTAMP,
                AdapterReplayBoundaryMode.LANDED_AT,
                AdapterReplayBoundaryMode.CURSOR,
            }
        )
    )
    request: BackfillBootstrapRequest = BackfillBootstrapRequest(
        desired_state=build_example_desired_state(),
        default_database="analytics",
        metadata_database="metadata",
        replay_lineage_mode="offsets",
    )

    with pytest.raises(AdapterCapabilityError) as error:
        bootstrap_module.execute_backfill_bootstrap(request=request, client=connection)

    interaction_count: int = len(connection.statements) + len(connection.catalog_databases)
    assert str(error.value) == test_case.expected_error_message
    assert interaction_count == test_case.expected_warehouse_interaction_count


@pytest.mark.parametrize(
    "test_case",
    [
        HistoryPrefixCapabilityTestCase(
            description="unsupported history-prefix seeding fails before writes",
            expected_error_message=("Adapter 'clickhouse' does not support history-prefix seeding"),
            expected_write_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_bounded_plan_when_adapter_cannot_seed_then_it_fails_before_writes(
    test_case: HistoryPrefixCapabilityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desired_state: DesiredState = build_example_desired_state()
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=ActualState(objects=()),
        default_database="analytics",
        render_resource=ClickHouseAdapter().render_resource,
        deployment_id="dep",
    )
    seeded_subtree: RebuildSubtree = replace(
        deployment_plan.rebuild_subtrees[0],
        execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    )
    seeded_plan: DeploymentPlan = replace(
        deployment_plan,
        rebuild_subtrees=(seeded_subtree,),
    )
    connection: RecordingAdapterConnection = RecordingAdapterConnection(history_prefix_seed=False)
    request: BackfillBootstrapRequest = BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database="analytics",
        metadata_database="metadata",
        replay_lineage_mode="offsets",
    )
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_unsupported_bounded_replay_behavior",
        lambda **_: seeded_plan,
    )

    with pytest.raises(AdapterCapabilityError) as error:
        bootstrap_module.execute_backfill_bootstrap(request=request, client=connection)

    write_count: int = sum(
        statement.startswith(("CREATE", "INSERT", "ALTER", "DROP", "RENAME"))
        for statement in connection.statements
    )
    assert str(error.value) == test_case.expected_error_message
    assert write_count == test_case.expected_write_count
