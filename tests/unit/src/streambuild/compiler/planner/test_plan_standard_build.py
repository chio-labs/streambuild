import pytest

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner._helpers.standard_ownership import classify_relation_ownership
from streambuild.compiler.planner.exceptions import StandardPlanError
from streambuild.compiler.planner.models import (
    StandardPlan,
    StandardWarehouseSnapshot,
    TargetOwnershipClassification,
)
from streambuild.compiler.planner.types import StandardPlanReason, TargetOwnership
from tests.unit.src.streambuild.compiler.planner._test_types import (
    StandardOwnershipTestCase,
    StandardPlanRejectionTestCase,
    StandardScopeTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_settled_standard_snapshot,
    build_standard_snapshot,
    logical_key_names,
    plan_standard_scope,
    relation_operation_summaries,
    replay_root_summaries,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardScopeTestCase(
            description="no selector rebuilds every model from the single source replay root",
            selected_model_names=(),
            expected_user_scope=(),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        ),
        StandardScopeTestCase(
            description="selecting the head model rebuilds the whole downstream closure",
            selected_model_names=("alpha",),
            expected_user_scope=("alpha",),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        ),
        StandardScopeTestCase(
            description="selecting the middle model keeps its parent preserved and out of scope",
            selected_model_names=("beta",),
            expected_user_scope=("beta",),
            expected_execution_scope=("beta", "gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("alpha",),
            expected_replay_roots=(
                ("beta", "tbl__alpha", ("beta", "gamma")),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
        StandardScopeTestCase(
            description="selecting a side-referenced model pulls in only its reference dependent",
            selected_model_names=("gamma",),
            expected_user_scope=("gamma",),
            expected_execution_scope=("gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("alpha", "beta"),
            expected_replay_roots=(
                ("gamma", "tbl__beta", ("gamma",)),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
        StandardScopeTestCase(
            description="selecting a leaf with two parents replays only from its driving parent",
            selected_model_names=("delta",),
            expected_user_scope=("delta",),
            expected_execution_scope=("delta",),
            expected_reasons=(StandardPlanReason.SELECTED,),
            expected_prerequisites=("alpha", "gamma"),
            expected_replay_roots=(("delta", "tbl__alpha", ("delta",)),),
        ),
        StandardScopeTestCase(
            description="overlapping selectors execute each closure member exactly once",
            selected_model_names=("gamma", "delta"),
            expected_user_scope=("gamma", "delta"),
            expected_execution_scope=("gamma", "delta"),
            expected_reasons=(StandardPlanReason.SELECTED, StandardPlanReason.SELECTED),
            expected_prerequisites=("alpha", "beta"),
            expected_replay_roots=(
                ("gamma", "tbl__beta", ("gamma",)),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selection_when_planning_standard_then_scope_and_replay_roots_match(
    standard_scope_analysis: CompileAnalysis, test_case: StandardScopeTestCase
) -> None:
    plan: StandardPlan = plan_standard_scope(
        analysis=standard_scope_analysis,
        snapshot=build_settled_standard_snapshot(),
        selected_model_names=test_case.selected_model_names,
    )

    assert logical_key_names(plan.user_scope) == test_case.expected_user_scope
    assert logical_key_names(plan.execution_scope) == test_case.expected_execution_scope
    assert tuple(entry.reason for entry in plan.entries) == test_case.expected_reasons
    assert (
        tuple(prerequisite.key.name for prerequisite in plan.prerequisite_scope)
        == test_case.expected_prerequisites
    )
    assert all(prerequisite.present for prerequisite in plan.prerequisite_scope)
    assert replay_root_summaries(plan=plan) == test_case.expected_replay_roots


@pytest.mark.parametrize(
    "test_case",
    [
        StandardScopeTestCase(
            description="a settled warehouse still plans the complete closure on every run",
            selected_model_names=(),
            expected_user_scope=(),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
                StandardPlanReason.ALL_MODELS,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_settled_warehouse_when_planning_standard_twice_then_plans_are_identical(
    standard_scope_analysis: CompileAnalysis, test_case: StandardScopeTestCase
) -> None:
    snapshot: StandardWarehouseSnapshot = build_settled_standard_snapshot()

    first_plan: StandardPlan = plan_standard_scope(
        analysis=standard_scope_analysis,
        snapshot=snapshot,
        selected_model_names=test_case.selected_model_names,
    )
    second_plan: StandardPlan = plan_standard_scope(
        analysis=standard_scope_analysis,
        snapshot=snapshot,
        selected_model_names=test_case.selected_model_names,
    )

    assert first_plan == second_plan
    assert logical_key_names(second_plan.execution_scope) == test_case.expected_execution_scope


@pytest.mark.parametrize(
    "test_case",
    [
        StandardScopeTestCase(
            description="teardown drops views before tables and creation reverses that order",
            selected_model_names=("beta",),
            expected_user_scope=("beta",),
            expected_execution_scope=("beta", "gamma", "delta"),
            expected_reasons=(
                StandardPlanReason.SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
                StandardPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("alpha",),
            expected_teardown=(
                ("drop", "mv__delta"),
                ("drop", "mv__gamma"),
                ("drop", "mv__beta"),
                ("drop", "tbl__delta"),
                ("drop", "tbl__gamma"),
                ("drop", "tbl__beta"),
            ),
            expected_creation=(
                ("create", "tbl__beta"),
                ("create", "tbl__gamma"),
                ("create", "tbl__delta"),
                ("create", "mv__beta"),
                ("create", "mv__gamma"),
                ("create", "mv__delta"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_executed_scope_when_planning_standard_then_relation_actions_are_dependency_safe(
    standard_scope_analysis: CompileAnalysis, test_case: StandardScopeTestCase
) -> None:
    plan: StandardPlan = plan_standard_scope(
        analysis=standard_scope_analysis,
        snapshot=build_settled_standard_snapshot(),
        selected_model_names=test_case.selected_model_names,
    )

    assert (
        relation_operation_summaries(operations=plan.teardown_operations)
        == test_case.expected_teardown
    )
    assert (
        relation_operation_summaries(operations=plan.creation_operations)
        == test_case.expected_creation
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardOwnershipTestCase(
            description="a relation absent from the warehouse is unclaimed",
            relation_names=(),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.ABSENT,),
        ),
        StandardOwnershipTestCase(
            description="a relation with a durable standard claim is standard owned",
            relation_names=("tbl__alpha",),
            standard_owned_names=("tbl__alpha",),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.STANDARD,),
        ),
        StandardOwnershipTestCase(
            description="a relation present without any durable claim is unmanaged",
            relation_names=("tbl__alpha",),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.UNMANAGED,),
        ),
        StandardOwnershipTestCase(
            description="a relation with a virtual-environment claim is virtual-environment owned",
            relation_names=("tbl__alpha",),
            standard_owned_names=(),
            virtual_environment_owned_names=("tbl__alpha",),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.VIRTUAL_ENVIRONMENT,),
        ),
        StandardOwnershipTestCase(
            description="a stable logical binding is virtual-environment owned without a record",
            relation_names=("tbl__alpha",),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=("tbl__alpha",),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.VIRTUAL_ENVIRONMENT,),
        ),
        StandardOwnershipTestCase(
            description="claims from both modes on one relation are conflicted",
            relation_names=("tbl__alpha",),
            standard_owned_names=("tbl__alpha",),
            virtual_environment_owned_names=("tbl__alpha",),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.CONFLICTED,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_durable_evidence_when_classifying_ownership_then_classification_matches(
    test_case: StandardOwnershipTestCase,
) -> None:
    snapshot: StandardWarehouseSnapshot = build_standard_snapshot(
        relation_names=test_case.relation_names,
        standard_owned_names=test_case.standard_owned_names,
        virtual_environment_owned_names=test_case.virtual_environment_owned_names,
        stable_binding_names=test_case.stable_binding_names,
    )

    classifications: tuple[TargetOwnershipClassification, ...] = classify_relation_ownership(
        snapshot=snapshot, relation_names=test_case.classified_relation_names
    )

    assert (
        tuple(classification.ownership for classification in classifications)
        == test_case.expected_ownership
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardPlanRejectionTestCase(
            description="a missing preserved prerequisite blocks the plan",
            selected_model_names=("beta",),
            present_relation_names=("raw__orders",),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            expected_error_fragment=(
                "Standard plan requires preserved upstream relations that do not exist: tbl__alpha"
            ),
        ),
        StandardPlanRejectionTestCase(
            description="a target claimed by virtual environments blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            standard_owned_names=(),
            virtual_environment_owned_names=("tbl__delta",),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is virtual_environment",
        ),
        StandardPlanRejectionTestCase(
            description="a stable logical binding on a target blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=("tbl__delta",),
            expected_error_fragment="tbl__delta is virtual_environment",
        ),
        StandardPlanRejectionTestCase(
            description="an unmanaged same-named relation blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            standard_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is unmanaged",
        ),
        StandardPlanRejectionTestCase(
            description="conflicting durable claims on a target block the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            standard_owned_names=("tbl__delta",),
            virtual_environment_owned_names=("tbl__delta",),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is conflicted",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_warehouse_state_when_planning_standard_then_planning_is_rejected(
    standard_scope_analysis: CompileAnalysis, test_case: StandardPlanRejectionTestCase
) -> None:
    snapshot: StandardWarehouseSnapshot = build_standard_snapshot(
        relation_names=test_case.present_relation_names,
        standard_owned_names=test_case.standard_owned_names,
        virtual_environment_owned_names=test_case.virtual_environment_owned_names,
        stable_binding_names=test_case.stable_binding_names,
    )

    with pytest.raises(StandardPlanError) as rejection:
        _ = plan_standard_scope(
            analysis=standard_scope_analysis,
            snapshot=snapshot,
            selected_model_names=test_case.selected_model_names,
        )

    assert test_case.expected_error_fragment in str(rejection.value)
