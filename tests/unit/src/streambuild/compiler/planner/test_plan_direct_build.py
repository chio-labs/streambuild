from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    AdapterReplayColumns,
    CatalogRelation,
)
from streambuild.compiler.compile.models import (
    DesiredState,
    ExternalSourceReplayConfig,
    ObjectKey,
)
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.discovery.types import ReplayBoundaryMode, SourceKind
from streambuild.compiler.pipeline.models import CompileAnalysis, RealizedProject
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectWarehouseSnapshot,
)
from streambuild.compiler.planner.types import (
    DirectPlanReason,
    DirectResourceKind,
    DirectSqlBaselineStatus,
)
from tests.unit.src.streambuild.compiler.planner._test_types import (
    DirectModelInputReplayColumnsTestCase,
    DirectMutableWarningTestCase,
    DirectPlanRejectionTestCase,
    DirectReplayInputCompatibilityTestCase,
    DirectScopeTestCase,
    DirectSqlChangeTestCase,
    DirectUndeclaredRelationTestCase,
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
    without_catalog_columns,
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
        DirectReplayInputCompatibilityTestCase(
            description="retained model lacks offset replay identity",
            selected_model_names=("delta",),
            replay_input_relation_name="tbl__alpha",
            removed_columns=("_replay_partition", "_replay_offset"),
            expected_error_fragment=(
                "cannot replay 'delta' from preserved upstream relation 'tbl__alpha': required "
                "replay columns are missing: _replay_partition, _replay_offset"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incompatible_replay_input_when_planning_direct_then_rejects_before_teardown(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectReplayInputCompatibilityTestCase,
) -> None:
    base_snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    snapshot: DirectWarehouseSnapshot = without_catalog_columns(
        snapshot=base_snapshot,
        relation_name=test_case.replay_input_relation_name,
        column_names=test_case.removed_columns,
    )

    with pytest.raises(DirectPlanError) as rejection:
        plan_direct_scope(
            analysis=direct_scope_analysis,
            snapshot=snapshot,
            selected_model_names=test_case.selected_model_names,
        )

    assert test_case.expected_error_fragment in str(rejection.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectUndeclaredRelationTestCase(
            description="an undeclared prior relation is outside the normal build scope",
            expected_preserved_relation_name="legacy_alpha",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_undeclared_prior_relation_when_planning_direct_then_normal_build_does_not_drop_it(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectUndeclaredRelationTestCase,
) -> None:
    base_snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    snapshot: DirectWarehouseSnapshot = replace(
        base_snapshot,
        catalog=replace(
            base_snapshot.catalog,
            relations=(
                *base_snapshot.catalog.relations,
                CatalogRelation(
                    name=test_case.expected_preserved_relation_name,
                    engine="View",
                    columns=(),
                ),
            ),
        ),
    )

    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=("alpha",),
    )

    teardown_names: tuple[str, ...] = tuple(
        operation.relation_name for operation in plan.teardown_operations
    )
    assert test_case.expected_preserved_relation_name not in teardown_names


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
        DirectSqlChangeTestCase(
            description="matching logical baseline explains equality without pruning",
            expected_status=DirectSqlBaselineStatus.NO_QUERY_CHANGE,
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_matching_direct_fingerprint_when_planning_then_selected_scope_still_executes(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectSqlChangeTestCase,
) -> None:
    current_sql: str = direct_scope_analysis.realized_project.project.models[0].query
    snapshot: DirectWarehouseSnapshot = replace(
        build_settled_direct_snapshot(),
        fingerprints=AdapterDirectFingerprintSnapshot(
            status="available",
            baselines=(
                AdapterDirectFingerprintRecord(
                    fingerprint_id="fingerprint-alpha",
                    logical_model_identity="analytics.alpha",
                    definition_sql=current_sql,
                    definition_hash=sha256(current_sql.encode()).hexdigest(),
                    identity_metadata="{}",
                    workflow_id="workflow-prior",
                    tool_version="test",
                    applied_at="2026-08-07 12:00:00.000",
                ),
            ),
        ),
    )

    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=(),
    )

    assert plan.entries[0].sql_change is not None
    assert plan.entries[0].sql_change.status == test_case.expected_status
    assert logical_key_names(plan.execution_scope) == test_case.expected_execution_scope


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSqlChangeTestCase(
            description="changed logical baseline produces a complete unified diff",
            expected_status=DirectSqlBaselineStatus.QUERY_CHANGED,
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_direct_fingerprint_when_planning_then_sql_diff_is_explanatory(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectSqlChangeTestCase,
) -> None:
    previous_sql: str = "SELECT 'previous' AS order_id"
    snapshot: DirectWarehouseSnapshot = replace(
        build_settled_direct_snapshot(),
        fingerprints=AdapterDirectFingerprintSnapshot(
            status="available",
            baselines=(
                AdapterDirectFingerprintRecord(
                    fingerprint_id="fingerprint-alpha",
                    logical_model_identity="analytics.alpha",
                    definition_sql=previous_sql,
                    definition_hash=sha256(previous_sql.encode()).hexdigest(),
                    identity_metadata="{}",
                    workflow_id="workflow-prior",
                    tool_version="test",
                    applied_at="2026-08-07 12:00:00.000",
                ),
            ),
        ),
    )

    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=(),
    )

    assert plan.entries[0].sql_change is not None
    assert plan.entries[0].sql_change.status == test_case.expected_status
    assert plan.entries[0].sql_change.previous_sql == previous_sql
    assert plan.entries[0].sql_change.unified_diff is not None
    assert logical_key_names(plan.execution_scope) == test_case.expected_execution_scope


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSqlChangeTestCase(
            description="unavailable baseline degrades explanation without pruning",
            expected_status=DirectSqlBaselineStatus.BASELINE_UNAVAILABLE,
            expected_execution_scope=("alpha", "beta", "gamma", "delta"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unavailable_direct_fingerprint_when_planning_then_scope_still_executes(
    direct_scope_analysis: CompileAnalysis,
    test_case: DirectSqlChangeTestCase,
) -> None:
    snapshot: DirectWarehouseSnapshot = replace(
        build_settled_direct_snapshot(),
        fingerprints=AdapterDirectFingerprintSnapshot(
            status="unavailable",
            baselines=(),
            warning="metadata denied",
        ),
    )

    plan: DirectPlan = plan_direct_scope(
        analysis=direct_scope_analysis,
        snapshot=snapshot,
        selected_model_names=(),
    )

    assert plan.entries[0].sql_change is not None
    assert plan.entries[0].sql_change.status == test_case.expected_status
    assert plan.entries[0].sql_change.warning == "metadata denied"
    assert logical_key_names(plan.execution_scope) == test_case.expected_execution_scope


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
        DirectPlanRejectionTestCase(
            description="a missing preserved prerequisite blocks the plan",
            selected_model_names=("beta",),
            present_relation_names=("raw__orders",),
            stable_binding_names=(),
            expected_error_fragment=(
                "Direct plan requires preserved upstream relations that do not exist: tbl__alpha"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_prerequisite_when_planning_direct_then_planning_is_rejected(
    direct_scope_analysis: CompileAnalysis, test_case: DirectPlanRejectionTestCase
) -> None:
    snapshot: DirectWarehouseSnapshot = build_direct_snapshot(
        relation_names=test_case.present_relation_names,
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
