from dataclasses import replace
from pathlib import Path

import pytest

from streambuild.adapter.models import (
    AdapterOwnershipRecord,
    AdapterReplayColumns,
    CatalogRelation,
)
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.compile.models import (
    DesiredState,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.discovery.types import ReplayBoundaryMode, SourceKind
from streambuild.compiler.pipeline.models import CompileAnalysis, RealizedProject
from streambuild.compiler.planner._helpers.direct_ownership import classify_relation_ownership
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectWarehouseSnapshot,
    TargetOwnershipClassification,
)
from streambuild.compiler.planner.types import (
    DirectPlanReason,
    DirectResourceKind,
    TargetOwnership,
)
from tests.unit.src.streambuild.compiler.planner._test_types import (
    DirectModelInputReplayColumnsTestCase,
    DirectMutableWarningTestCase,
    DirectOwnershipTestCase,
    DirectPlanRejectionTestCase,
    DirectRenameTeardownTestCase,
    DirectScopeTestCase,
    DirectViewPlanTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    analyze_direct_scope_project,
    build_direct_snapshot,
    build_settled_direct_snapshot,
    logical_key_names,
    plan_direct_scope,
    relation_operation_summaries,
    replay_root_summaries,
    write_direct_multi_upstream_view_project,
    write_direct_mutable_scope_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectScopeTestCase(
            description="no selector rebuilds every model from the single source replay root",
            selected_model_names=(),
            expected_user_scope=(),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        ),
        DirectScopeTestCase(
            description="selecting the head model rebuilds the whole downstream closure",
            selected_model_names=("alpha",),
            expected_user_scope=("alpha",),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        ),
        DirectScopeTestCase(
            description="selecting the middle model keeps its parent preserved and out of scope",
            selected_model_names=("beta",),
            expected_user_scope=("beta",),
            expected_execution_scope=("beta", "gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("alpha",),
            expected_replay_roots=(
                ("beta", "tbl__alpha", ("beta", "gamma")),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
        DirectScopeTestCase(
            description="selecting a side-referenced model pulls in only its reference dependent",
            selected_model_names=("gamma",),
            expected_user_scope=("gamma",),
            expected_execution_scope=("gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
            ),
            expected_prerequisites=("alpha", "beta"),
            expected_replay_roots=(
                ("gamma", "tbl__beta", ("gamma",)),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
        DirectScopeTestCase(
            description="selecting a leaf with two parents replays only from its driving parent",
            selected_model_names=("delta",),
            expected_user_scope=("delta",),
            expected_execution_scope=("delta",),
            expected_reasons=(DirectPlanReason.SELECTED,),
            expected_prerequisites=("alpha", "gamma"),
            expected_replay_roots=(("delta", "tbl__alpha", ("delta",)),),
        ),
        DirectScopeTestCase(
            description="overlapping selectors execute each closure member exactly once",
            selected_model_names=("gamma", "delta"),
            expected_user_scope=("gamma", "delta"),
            expected_execution_scope=("gamma", "delta"),
            expected_reasons=(DirectPlanReason.SELECTED, DirectPlanReason.SELECTED),
            expected_prerequisites=("alpha", "beta"),
            expected_replay_roots=(
                ("gamma", "tbl__beta", ("gamma",)),
                ("delta", "tbl__alpha", ("delta",)),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selection_when_planning_direct_then_scope_and_replay_roots_match(
    direct_scope_analysis: CompileAnalysis, test_case: DirectScopeTestCase
) -> None:
    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=build_settled_direct_snapshot(),
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
        DirectRenameTeardownTestCase(
            description="tears down prior direct-owned relation for executed logical model",
            selected_model_names=("alpha",),
            stale_relation_name="legacy_alpha",
            stale_logical_model_name="alpha",
            owning_mode="direct",
            expected_stale_teardown=True,
        ),
        DirectRenameTeardownTestCase(
            description="does not tear down relation owned by model outside execution scope",
            selected_model_names=("gamma",),
            stale_relation_name="legacy_beta",
            stale_logical_model_name="beta",
            owning_mode="direct",
            expected_stale_teardown=False,
        ),
        DirectRenameTeardownTestCase(
            description="does not tear down virtual-environment relation for matching model",
            selected_model_names=("alpha",),
            stale_relation_name="legacy_alpha",
            stale_logical_model_name="alpha",
            owning_mode="virtual_environment",
            expected_stale_teardown=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_prior_relation_when_planning_direct_then_only_owned_model_rename_is_torn_down(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectRenameTeardownTestCase,
) -> None:
    base_snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    snapshot: DirectWarehouseSnapshot = replace(
        base_snapshot,
        catalog=replace(
            base_snapshot.catalog,
            relations=(
                *base_snapshot.catalog.relations,
                CatalogRelation(
                    name=test_case.stale_relation_name,
                    engine="View",
                    columns=(),
                ),
            ),
        ),
        ownership_records=(
            *base_snapshot.ownership_records,
            AdapterOwnershipRecord(
                database_name="analytics",
                relation_name=test_case.stale_relation_name,
                resource_kind=DirectResourceKind.VIEW,
                logical_model_name=test_case.stale_logical_model_name,
                owning_mode=AdapterOwningMode(test_case.owning_mode),
                tool_version="test",
            ),
        ),
    )

    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=test_case.selected_model_names,
    )

    teardown_names: tuple[str, ...] = tuple(
        operation.relation_name for operation in plan.teardown_operations
    )
    assert (test_case.stale_relation_name in teardown_names) is test_case.expected_stale_teardown


@pytest.mark.parametrize(
    "test_case",
    [
        DirectViewPlanTestCase(
            description="selected multi-upstream view is query-only with explicit view identity",
            selected_model_names=("customer_orders",),
            present_relation_names=("raw__orders", "orders_rollup"),
            expected_relation_name="customer_orders",
            expected_prerequisites=("orders", "orders_base"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_terminal_view_when_planning_direct_then_it_has_no_replay_work(
    test_case: DirectViewPlanTestCase, tmp_path: Path
) -> None:
    write_direct_multi_upstream_view_project(project_root=tmp_path)
    analysis: CompileAnalysis = analyze_direct_scope_project(project_root=tmp_path)
    plan: DirectPlan = plan_direct_scope(
        analysis=analysis,
        snapshot=build_direct_snapshot(relation_names=test_case.present_relation_names),
        selected_model_names=test_case.selected_model_names,
    )

    assert logical_key_names(plan.execution_scope) == test_case.selected_model_names
    assert (
        tuple(prerequisite.key.name for prerequisite in plan.prerequisite_scope)
        == test_case.expected_prerequisites
    )
    assert plan.entries[0].relation_names == (test_case.expected_relation_name,)
    assert plan.entries[0].resource_kinds == (DirectResourceKind.VIEW,)
    assert plan.entries[0].driving_input_key is None
    assert plan.replay_roots == ()
    assert tuple(operation.resource_kind for operation in plan.teardown_operations) == (
        DirectResourceKind.VIEW,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DirectScopeTestCase(
            description="a settled warehouse still plans the complete closure on every run",
            selected_model_names=(),
            expected_user_scope=(),
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
                DirectPlanReason.ALL_MODELS,
            ),
            expected_prerequisites=("orders",),
            expected_replay_roots=(("alpha", "raw__orders", ("alpha", "beta", "gamma", "delta")),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_settled_warehouse_when_planning_direct_twice_then_plans_are_identical(
    direct_scope_analysis: CompileAnalysis, test_case: DirectScopeTestCase
) -> None:
    snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()

    first_plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=test_case.selected_model_names,
    )
    second_plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=test_case.selected_model_names,
    )

    assert first_plan == second_plan
    assert logical_key_names(second_plan.execution_scope) == test_case.expected_execution_scope


@pytest.mark.parametrize(
    "test_case",
    [
        DirectScopeTestCase(
            description="teardown drops views before tables and creation reverses that order",
            selected_model_names=("beta",),
            expected_user_scope=("beta",),
            expected_execution_scope=("beta", "gamma", "delta"),
            expected_reasons=(
                DirectPlanReason.SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
                DirectPlanReason.DOWNSTREAM_OF_SELECTED,
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
def test_given_executed_scope_when_planning_direct_then_relation_actions_are_dependency_safe(
    direct_scope_analysis: CompileAnalysis, test_case: DirectScopeTestCase
) -> None:
    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=build_settled_direct_snapshot(),
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
        DirectOwnershipTestCase(
            description="a relation absent from the warehouse is unclaimed",
            relation_names=(),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.ABSENT,),
        ),
        DirectOwnershipTestCase(
            description="a relation with a durable direct claim is direct owned",
            relation_names=("tbl__alpha",),
            direct_owned_names=("tbl__alpha",),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.DIRECT,),
        ),
        DirectOwnershipTestCase(
            description="a relation present without any durable claim is unmanaged",
            relation_names=("tbl__alpha",),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.UNMANAGED,),
        ),
        DirectOwnershipTestCase(
            description="a claim for the same relation in another database is ignored",
            relation_names=("tbl__alpha",),
            direct_owned_names=("tbl__alpha",),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.UNMANAGED,),
            ownership_database="other_database",
        ),
        DirectOwnershipTestCase(
            description="a relation with a virtual-environment claim is virtual-environment owned",
            relation_names=("tbl__alpha",),
            direct_owned_names=(),
            virtual_environment_owned_names=("tbl__alpha",),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.VIRTUAL_ENVIRONMENT,),
        ),
        DirectOwnershipTestCase(
            description="a stable logical binding is virtual-environment owned without a record",
            relation_names=("tbl__alpha",),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=("tbl__alpha",),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.VIRTUAL_ENVIRONMENT,),
        ),
        DirectOwnershipTestCase(
            description="metadata-only virtual deployment blocks a missing direct target",
            relation_names=(),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.VIRTUAL_ENVIRONMENT,),
            metadata_virtual_environment_names=("tbl__alpha",),
        ),
        DirectOwnershipTestCase(
            description="claims from both modes on one relation are conflicted",
            relation_names=("tbl__alpha",),
            direct_owned_names=("tbl__alpha",),
            virtual_environment_owned_names=("tbl__alpha",),
            stable_binding_names=(),
            classified_relation_names=("tbl__alpha",),
            expected_ownership=(TargetOwnership.CONFLICTED,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_durable_evidence_when_classifying_ownership_then_classification_matches(
    test_case: DirectOwnershipTestCase,
) -> None:
    snapshot: DirectWarehouseSnapshot = build_direct_snapshot(
        relation_names=test_case.relation_names,
        direct_owned_names=test_case.direct_owned_names,
        virtual_environment_owned_names=test_case.virtual_environment_owned_names,
        stable_binding_names=test_case.stable_binding_names,
        ownership_database=test_case.ownership_database,
        metadata_virtual_environment_names=test_case.metadata_virtual_environment_names,
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
        DirectPlanRejectionTestCase(
            description="a missing preserved prerequisite blocks the plan",
            selected_model_names=("beta",),
            present_relation_names=("raw__orders",),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            expected_error_fragment=(
                "Direct plan requires preserved upstream relations that do not exist: tbl__alpha"
            ),
        ),
        DirectPlanRejectionTestCase(
            description="a target claimed by virtual environments blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            direct_owned_names=(),
            virtual_environment_owned_names=("tbl__delta",),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is virtual_environment",
        ),
        DirectPlanRejectionTestCase(
            description="a stable logical binding on a target blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=("tbl__delta",),
            expected_error_fragment="tbl__delta is virtual_environment",
        ),
        DirectPlanRejectionTestCase(
            description="an unmanaged same-named relation blocks the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            direct_owned_names=(),
            virtual_environment_owned_names=(),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is unmanaged",
        ),
        DirectPlanRejectionTestCase(
            description="conflicting durable claims on a target block the plan",
            selected_model_names=("delta",),
            present_relation_names=("raw__orders", "tbl__alpha", "tbl__gamma", "tbl__delta"),
            direct_owned_names=("tbl__delta",),
            virtual_environment_owned_names=("tbl__delta",),
            stable_binding_names=(),
            expected_error_fragment="tbl__delta is conflicted",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_warehouse_state_when_planning_direct_then_planning_is_rejected(
    direct_scope_analysis: CompileAnalysis, test_case: DirectPlanRejectionTestCase
) -> None:
    snapshot: DirectWarehouseSnapshot = build_direct_snapshot(
        relation_names=test_case.present_relation_names,
        direct_owned_names=test_case.direct_owned_names,
        virtual_environment_owned_names=test_case.virtual_environment_owned_names,
        stable_binding_names=test_case.stable_binding_names,
    )

    with pytest.raises(DirectPlanError) as rejection:
        _ = plan_direct_scope(
            analysis=direct_scope_analysis,
            snapshot=snapshot,
            selected_model_names=test_case.selected_model_names,
        )

    assert test_case.expected_error_fragment in str(rejection.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectMutableWarningTestCase(
            description="executed mutable side reference emits replay warning",
            expected_warning_code="mutable_ref_replay_not_guaranteed",
            expected_warning_fragment="exact historical replay equivalence cannot be guaranteed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mutable_side_reference_when_planning_direct_then_warning_is_emitted(
    test_case: DirectMutableWarningTestCase, tmp_path: Path
) -> None:
    write_direct_mutable_scope_project(project_root=tmp_path)
    analysis: CompileAnalysis = analyze_direct_scope_project(project_root=tmp_path)

    plan: DirectPlan = plan_direct_scope(
        analysis=analysis,
        snapshot=build_settled_direct_snapshot(),
        selected_model_names=("delta",),
    )

    assert tuple(warning.warning_code for warning in plan.warnings) == (
        test_case.expected_warning_code,
    )
    assert test_case.expected_warning_fragment in plan.warnings[0].message


@pytest.mark.parametrize(
    "test_case",
    [
        DirectModelInputReplayColumnsTestCase(
            description="preserved model input ignores unrelated adopted physical mapping",
            expected_replay_columns=(
                "_replay_partition",
                "_replay_offset",
                "_replay_timestamp",
                "_replay_landed_at",
                "_replay_cursor",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_input_name_matching_adopted_relation_when_planning_then_columns_are_canonical(
    test_case: DirectModelInputReplayColumnsTestCase, tmp_path: Path
) -> None:
    write_direct_mutable_scope_project(project_root=tmp_path)
    analysis: CompileAnalysis = analyze_direct_scope_project(project_root=tmp_path)
    desired_state: DesiredState = replace(
        analysis.realized_project.desired_state,
        external_source_replay_configs=(
            ExternalSourceReplayConfig(
                key=ObjectKey(
                    database=None,
                    object_type=DesiredObjectType.TABLE,
                    name="tbl__alpha",
                ),
                table_name="tbl__alpha",
                source_kind=SourceKind.STREAM_TABLE,
                replay_boundary_mode=ReplayBoundaryMode.OFFSETS,
                partition_column_name="external_partition",
                offset_column_name="external_offset",
                timestamp_column_name="external_timestamp",
            ),
        ),
    )
    realized_project: RealizedProject = replace(
        analysis.realized_project, desired_state=desired_state
    )
    mutated_analysis: CompileAnalysis = replace(analysis, realized_project=realized_project)

    plan: DirectPlan = plan_direct_scope(
        analysis=mutated_analysis,
        snapshot=build_settled_direct_snapshot(),
        selected_model_names=("beta",),
    )

    replay_columns: AdapterReplayColumns = plan.replay_roots[0].driving_input_replay_columns
    assert (
        replay_columns.partition,
        replay_columns.offset,
        replay_columns.timestamp,
        replay_columns.landed_at,
        replay_columns.cursor,
    ) == test_case.expected_replay_columns
