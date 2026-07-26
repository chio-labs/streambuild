import pytest

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    DesiredState,
)
from streambuild.compiler.desired_state.main.build_desired_state import build_desired_state
from streambuild.compiler.discovery.types import ReplayBoundaryMode, ReplayLineageMode
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import ActualState, DeploymentPlan
from streambuild.compiler.planner.types import DeploymentAction
from tests.unit.src.streambuild.compiler.planner._test_types import (
    PlannerPreservationMatrixTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_preservation_matrix_compiled_pipeline,
    key_parts,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlannerPreservationMatrixTestCase(
            description="plans managed Kafka offset replay",
            source_ownership="managed",
            replay_lineage_mode=ReplayLineageMode.OFFSETS,
            expected_source_type=CompiledManagedSource,
            expected_desired_object_count=5,
            expected_external_replay_boundary_modes=(),
            expected_upstream_boundary_key=(None, "table", "raw__orders"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
        PlannerPreservationMatrixTestCase(
            description="plans managed Kafka timestamp replay",
            source_ownership="managed",
            replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
            expected_source_type=CompiledManagedSource,
            expected_desired_object_count=5,
            expected_external_replay_boundary_modes=(),
            expected_upstream_boundary_key=(None, "table", "raw__orders"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
        PlannerPreservationMatrixTestCase(
            description="plans managed Kafka landed-at replay",
            source_ownership="managed",
            replay_lineage_mode=ReplayLineageMode.LANDED_AT,
            expected_source_type=CompiledManagedSource,
            expected_desired_object_count=5,
            expected_external_replay_boundary_modes=(),
            expected_upstream_boundary_key=(None, "table", "raw__orders"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
        PlannerPreservationMatrixTestCase(
            description="plans adopted external offset replay",
            source_ownership="adopted",
            replay_lineage_mode=ReplayLineageMode.OFFSETS,
            expected_source_type=CompiledExternalSource,
            expected_desired_object_count=2,
            expected_external_replay_boundary_modes=(ReplayBoundaryMode.OFFSETS,),
            expected_upstream_boundary_key=(None, "table", "orders_existing"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
        PlannerPreservationMatrixTestCase(
            description="plans adopted external timestamp replay",
            source_ownership="adopted",
            replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
            expected_source_type=CompiledExternalSource,
            expected_desired_object_count=2,
            expected_external_replay_boundary_modes=(ReplayBoundaryMode.TIMESTAMP,),
            expected_upstream_boundary_key=(None, "table", "orders_existing"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
        PlannerPreservationMatrixTestCase(
            description="plans adopted external cursor replay",
            source_ownership="adopted",
            replay_lineage_mode=ReplayLineageMode.CURSOR,
            expected_source_type=CompiledExternalSource,
            expected_desired_object_count=2,
            expected_external_replay_boundary_modes=(ReplayBoundaryMode.CURSOR,),
            expected_upstream_boundary_key=(None, "table", "orders_existing"),
            expected_actions=(
                DeploymentAction.PLAN_SHADOW_TABLE,
                DeploymentAction.PLAN_SHADOW_MATERIALIZED_VIEW,
                DeploymentAction.BACKFILL_SUBTREE,
                DeploymentAction.AUDIT_SUBTREE,
                DeploymentAction.PUBLISH_SUBTREE,
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_source_mode_pair_when_planning_then_preserves_rebuild_plan(
    test_case: PlannerPreservationMatrixTestCase,
) -> None:
    compiled_pipeline: CompiledPipeline = build_preservation_matrix_compiled_pipeline(
        source_ownership=test_case.source_ownership,
        replay_lineage_mode=test_case.replay_lineage_mode,
    )
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=desired_state,
        actual_state=ActualState(objects=()),
        default_database="analytics",
        render_resource=ClickHouseAdapter().render_resource,
    )

    assert isinstance(compiled_pipeline.source, test_case.expected_source_type)
    assert compiled_pipeline.effective_replay_lineage_mode == test_case.replay_lineage_mode
    assert len(desired_state.objects) == test_case.expected_desired_object_count
    assert (
        tuple(
            config.replay_boundary_mode for config in desired_state.external_source_replay_configs
        )
        == test_case.expected_external_replay_boundary_modes
    )
    assert tuple(
        key_parts(subtree.upstream_boundary_key) for subtree in deployment_plan.rebuild_subtrees
    ) == (test_case.expected_upstream_boundary_key,)
    assert tuple(step.action for step in deployment_plan.steps) == test_case.expected_actions
