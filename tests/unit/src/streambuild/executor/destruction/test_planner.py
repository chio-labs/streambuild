from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from streambuild.adapter.models import (
    AdapterDeploymentRecord,
    AdapterMetadataObjectKey,
    AdapterOwnedResourceEvent,
    AdapterOwnedResourceSnapshot,
    AdapterPreparedObjectMapping,
    AdapterPublishEventRecord,
    AdapterStableBinding,
    CatalogRelation,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.destruction.exceptions import (
    DestructionConsistencyError,
    DestructionDependencyError,
    DestructionExternalDependencyError,
    DestructionResourceError,
    DestructionSelectionError,
)
from streambuild.executor.destruction.main.build_destruction_challenges import (
    build_destruction_challenges,
)
from streambuild.executor.destruction.main.plan_destruction import plan_destruction
from streambuild.executor.destruction.models import (
    DestructionPlan,
    DestructionRelationEvidence,
    DestructionRequest,
)
from streambuild.executor.destruction.types import (
    DestructionOperation,
    DestructionOwnership,
)
from tests.unit.src.streambuild.executor.destruction._test_types import (
    DestructionChallengeTestCase,
    DestructionClosureTestCase,
    DestructionDependencyTestCase,
    DuplicateSelectionTestCase,
    OwnershipLedgerBehaviorTestCase,
    PipelineDestructionPlanTestCase,
    PreservedSourceClosureTestCase,
    StableDriftFingerprintTestCase,
    StableFingerprintTestCase,
    StaleLedgerImpactTestCase,
    TargetResetPlanTestCase,
    VirtualHistoryResetTestCase,
    WarehouseDependencyFailureTestCase,
)
from tests.unit.src.streambuild.executor.destruction.helpers import (
    PlanningFixture,
    build_model_dependency_planning_fixture,
    build_planning_fixture,
    build_source_dependency_planning_fixture,
)

_NOW: datetime = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionChallengeTestCase(
            description="one pipeline requires its exact name",
            pipeline_names=("alpha",),
            production_reset=False,
            expected_challenges=("alpha",),
        ),
        DestructionChallengeTestCase(
            description="three pipelines require all sorted names",
            pipeline_names=("charlie", "alpha", "beta"),
            production_reset=False,
            expected_challenges=("alpha", "beta", "charlie"),
        ),
        DestructionChallengeTestCase(
            description="larger sets require first middle and last sorted names",
            pipeline_names=("echo", "alpha", "delta", "bravo", "charlie"),
            production_reset=False,
            expected_challenges=("alpha", "charlie", "echo"),
        ),
        DestructionChallengeTestCase(
            description="production reset appends the production challenge",
            pipeline_names=("beta", "alpha"),
            production_reset=True,
            expected_challenges=("alpha", "beta", "PRODUCTION"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_affected_names_when_building_challenges_then_rules_are_deterministic(
    test_case: DestructionChallengeTestCase,
) -> None:
    challenges: tuple[str, ...] = build_destruction_challenges(
        pipeline_names=test_case.pipeline_names,
        production_reset=test_case.production_reset,
    )

    assert challenges == test_case.expected_challenges


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionDependencyTestCase(
            description="an unselected model downstream pipeline blocks destruction",
            fixture_builder=build_model_dependency_planning_fixture,
            expected_dependent_pipeline_names=("beta",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unselected_downstream_pipeline_when_planning_then_dependency_blocks(
    test_case: DestructionDependencyTestCase,
) -> None:
    fixture: PlanningFixture = test_case.fixture_builder()

    with pytest.raises(DestructionDependencyError) as raised:
        plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="uat",
                database="analytics",
                metadata_database="metadata",
                pipeline_names=("alpha",),
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
            now=_NOW,
        )

    assert raised.value.dependent_pipeline_names == test_case.expected_dependent_pipeline_names


@pytest.mark.parametrize(
    "test_case",
    [
        PreservedSourceClosureTestCase(
            description="shared preserved source does not create pipeline destruction closure",
            expected_affected_pipeline_names=("alpha",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shared_preserved_source_when_planning_then_downstream_pipeline_is_not_required(
    test_case: PreservedSourceClosureTestCase,
) -> None:
    fixture: PlanningFixture = build_source_dependency_planning_fixture()

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="destroy_pipelines",
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha",),
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
        now=_NOW,
    )

    assert plan.affected_pipeline_names == test_case.expected_affected_pipeline_names
    assert plan.included_dependent_pipeline_names == ()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionClosureTestCase(
            description="an explicit downstream closure unblocks destruction",
            expected_requested_pipeline_names=("alpha",),
            expected_included_pipeline_names=("beta",),
            expected_affected_pipeline_names=("alpha", "beta"),
            expected_affected_model_names=("orders", "summary"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_downstream_closure_when_planning_then_destruction_is_unblocked(
    test_case: DestructionClosureTestCase,
) -> None:
    fixture: PlanningFixture = build_model_dependency_planning_fixture()

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="destroy_pipelines",
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha",),
            included_dependent_pipeline_names=("beta",),
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
        now=_NOW,
    )

    assert plan.requested_pipeline_names == test_case.expected_requested_pipeline_names
    assert plan.included_dependent_pipeline_names == test_case.expected_included_pipeline_names
    assert plan.affected_pipeline_names == test_case.expected_affected_pipeline_names
    assert plan.affected_model_names == test_case.expected_affected_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        PipelineDestructionPlanTestCase(
            description="pipeline destruction contains only exact owned model relations",
            expected_relation_names=(
                "mv__orders",
                "tbl__orders",
                "tbl__orders__deployment_1",
            ),
            expected_excluded_relation_names=(
                "tbl__orders_backup",
                "old__orders__deployment_1",
                "kafka__events",
                "raw__events",
            ),
            expected_affected_source_names=(),
            expected_preserves_sources=True,
            expected_preserves_replay_data=True,
            expected_stable_ownership=(
                DestructionOwnership.CURRENT_MANIFEST,
                DestructionOwnership.PUBLISHED_STABLE_BINDING,
            ),
            expected_total_bytes=2048,
            expected_active_parts=2,
            expected_catalog_databases=["analytics"],
            expected_inventory_databases=["metadata"],
            expected_query_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_destruction_when_planning_then_only_exact_owned_model_relations_exist(
    test_case: PipelineDestructionPlanTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation=DestructionOperation.DESTROY_PIPELINES,
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha",),
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
        now=_NOW,
        plan_id="fixed-plan",
    )
    by_name: dict[str, DestructionRelationEvidence] = {
        relation.name: relation for relation in plan.relations
    }

    assert tuple(by_name) == test_case.expected_relation_names
    assert set(test_case.expected_excluded_relation_names).isdisjoint(by_name)
    assert plan.affected_source_names == test_case.expected_affected_source_names
    assert plan.preserves_sources is test_case.expected_preserves_sources
    assert plan.preserves_replay_data is test_case.expected_preserves_replay_data
    assert by_name["tbl__orders"].ownership == test_case.expected_stable_ownership
    assert by_name["tbl__orders__deployment_1"].total_bytes == test_case.expected_total_bytes
    assert by_name["tbl__orders__deployment_1"].active_parts == test_case.expected_active_parts
    assert fixture.connection.catalog_databases == test_case.expected_catalog_databases
    assert fixture.connection.inventory_databases == test_case.expected_inventory_databases
    assert len(fixture.connection.queries) == test_case.expected_query_count
    with pytest.raises(FrozenInstanceError):
        setattr(plan, "".join(("tar", "get")), "other")


@pytest.mark.parametrize(
    "test_case",
    [
        TargetResetPlanTestCase(
            description="target reset includes managed sources but excludes adopted sources",
            expected_included_relation_names=(
                "kafka__events",
                "raw__events",
                "raw__events__deployment_1",
                "mv__events",
            ),
            expected_excluded_relation_names=(
                "external_users",
                "_streambuild_manifest_accident",
            ),
            expected_affected_source_names=("events",),
            expected_preserves_sources=False,
            expected_preserves_replay_data=False,
            expected_challenges=("alpha", "beta", "PRODUCTION"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_reset_when_planning_then_sources_include_managed_but_not_adopted(
    test_case: TargetResetPlanTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture(target_name="production")

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="production",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
        now=_NOW,
    )
    relation_names: tuple[str, ...] = tuple(relation.name for relation in plan.relations)

    assert set(test_case.expected_included_relation_names).issubset(relation_names)
    assert set(test_case.expected_excluded_relation_names).isdisjoint(relation_names)
    assert plan.affected_source_names == test_case.expected_affected_source_names
    assert plan.preserves_sources is test_case.expected_preserves_sources
    assert plan.preserves_replay_data is test_case.expected_preserves_replay_data
    assert plan.challenges == test_case.expected_challenges


@pytest.mark.parametrize(
    "test_case",
    [
        StableFingerprintTestCase(
            description="equivalent current state has stable fingerprints",
            expected_fingerprint_length=64,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equivalent_current_state_when_replanning_then_fingerprints_are_stable(
    test_case: StableFingerprintTestCase,
) -> None:
    first_fixture: PlanningFixture = build_planning_fixture()
    second_fixture: PlanningFixture = build_planning_fixture()
    request: DestructionRequest = DestructionRequest(
        operation="destroy_pipelines",
        target="uat",
        database="analytics",
        metadata_database="metadata",
        pipeline_names=("alpha",),
    )

    first: DestructionPlan = plan_destruction(
        request=request,
        analysis=first_fixture.analysis,
        connection=first_fixture.connection,
        now=_NOW,
        plan_id="first",
    )
    second: DestructionPlan = plan_destruction(
        request=request,
        analysis=second_fixture.analysis,
        connection=second_fixture.connection,
        now=_NOW.replace(hour=13),
        plan_id="second",
    )

    assert first.manifest_fingerprint == second.manifest_fingerprint
    assert first.plan_fingerprint == second.plan_fingerprint
    assert len(first.manifest_fingerprint) == test_case.expected_fingerprint_length
    assert len(first.plan_fingerprint) == test_case.expected_fingerprint_length


@pytest.mark.parametrize(
    "test_case",
    [
        StableDriftFingerprintTestCase(
            description="part and byte changes do not alter the drift fingerprint",
            changed_stats=(("tbl__orders__deployment_1", 8192, 8),),
            expected_estimated_bytes_changed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_only_part_bytes_change_when_replanning_then_drift_fingerprint_is_stable(
    test_case: StableDriftFingerprintTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    request: DestructionRequest = DestructionRequest(
        operation="destroy_pipelines",
        target="uat",
        database="analytics",
        metadata_database="metadata",
        pipeline_names=("alpha",),
    )
    first: DestructionPlan = plan_destruction(
        request=request, analysis=fixture.analysis, connection=fixture.connection
    )
    fixture.connection.stats = test_case.changed_stats

    second: DestructionPlan = plan_destruction(
        request=request, analysis=fixture.analysis, connection=fixture.connection
    )

    assert (
        second.estimated_bytes != first.estimated_bytes
    ) is test_case.expected_estimated_bytes_changed
    assert second.plan_fingerprint == first.plan_fingerprint


@pytest.mark.parametrize(
    "test_case",
    [
        DuplicateSelectionTestCase(
            description="a duplicate pipeline selection is rejected",
            expected_error_match="duplicate",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_pipeline_when_creating_request_then_selection_is_rejected(
    test_case: DuplicateSelectionTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_match):
        DestructionRequest(
            operation="destroy_pipelines",
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha", "alpha"),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="stale recorded relation is reset",
            expected_value="legacy_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_stale_recorded_relation_when_resetting_then_historical_resource_is_included(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=(
            AdapterOwnedResourceEvent(
                event_id="owned-old",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name="legacy_orders",
                resource_kind="table",
                pipeline_name="alpha",
                logical_resource_type="model",
                logical_resource_name="orders",
                resource_role="model_table",
                catalog_fingerprint=None,
            ),
        ),
    )

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="uat",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )

    assert test_case.expected_value in {relation.name for relation in plan.relations}


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="recorded source is preserved then reset",
            expected_value="stale_raw_events",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_source_when_destroying_pipeline_then_source_is_preserved(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=(
            AdapterOwnedResourceEvent(
                event_id="owned-source",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name="stale_raw_events",
                resource_kind="table",
                pipeline_name="alpha",
                logical_resource_type="source",
                logical_resource_name="events",
                resource_role="source_replay_table",
                catalog_fingerprint=None,
            ),
        ),
    )

    destroy: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="destroy_pipelines",
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha",),
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )
    reset: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="uat",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )

    assert test_case.expected_value not in {relation.name for relation in destroy.relations}
    assert test_case.expected_value in {relation.name for relation in reset.relations}


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="manual replacement is refused",
            expected_value="not the generation recorded",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manually_replaced_owned_relation_when_planning_then_destruction_is_refused(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.catalog = replace(
        fixture.connection.catalog,
        relations=(
            replace(
                fixture.connection.catalog.relations[0],
                ownership_generation="replacement-generation",
            ),
            *fixture.connection.catalog.relations[1:],
        ),
    )
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=(
            AdapterOwnedResourceEvent(
                event_id="owned-orders",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name="tbl__orders",
                resource_kind="view",
                pipeline_name="alpha",
                logical_resource_type="model",
                logical_resource_name="orders",
                resource_role="stable_binding",
                catalog_fingerprint="original-generation",
            ),
        ),
    )

    with pytest.raises(DestructionResourceError, match=test_case.expected_value):
        plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="uat",
                database="analytics",
                metadata_database="metadata",
                pipeline_names=("alpha",),
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualHistoryResetTestCase(
            description="reset includes retired pre-ledger virtual history",
            expected_reset_relation_names=("retired_binding", "retired_physical"),
            expected_destroy_excluded_names=("retired_binding", "retired_physical"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_retired_virtual_history_when_planning_then_only_reset_includes_relations(
    test_case: VirtualHistoryResetTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    deployment: AdapterDeploymentRecord = fixture.connection.inventory.deployments[0]
    stale_mapping: AdapterPreparedObjectMapping = AdapterPreparedObjectMapping(
        logical_key=AdapterMetadataObjectKey(
            database=None,
            object_type="table",
            name="retired_binding",
        ),
        physical_name="retired_physical",
        logical_model_name="retired_model",
    )
    fixture.connection.inventory = replace(
        fixture.connection.inventory,
        deployments=(
            replace(
                deployment,
                prepared_object_mappings=(
                    *deployment.prepared_object_mappings,
                    stale_mapping,
                ),
            ),
        ),
        publish_events=(
            *fixture.connection.inventory.publish_events,
            AdapterPublishEventRecord(
                deployment_id=deployment.deployment_id,
                published_at="2026-08-24 11:00:00.000",
                logical_view_names=("retired_binding",),
                bindings=(
                    AdapterStableBinding(
                        database="analytics",
                        logical_name="retired_binding",
                        physical_name="retired_physical",
                    ),
                ),
            ),
        ),
    )
    reset: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="uat",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )
    destroy: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="destroy_pipelines",
            target="uat",
            database="analytics",
            metadata_database="metadata",
            pipeline_names=("alpha",),
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )

    reset_names: frozenset[str] = frozenset(relation.name for relation in reset.relations)
    destroy_names: frozenset[str] = frozenset(relation.name for relation in destroy.relations)
    assert set(test_case.expected_reset_relation_names) <= reset_names
    assert set(test_case.expected_destroy_excluded_names).isdisjoint(destroy_names)


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="live retired name reuse lacks generation authority",
            expected_value="historical deployment metadata does not prove ownership",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_live_preledger_history_when_resetting_then_external_reuse_is_refused(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.catalog = replace(
        fixture.connection.catalog,
        relations=(
            *fixture.connection.catalog.relations,
            CatalogRelation(name="old__orders__deployment_1", engine="MergeTree", columns=()),
        ),
    )

    with pytest.raises(DestructionResourceError, match=test_case.expected_value):
        plan_destruction(
            request=DestructionRequest(
                operation="reset_target",
                target="uat",
                database="analytics",
                metadata_database="metadata",
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="committed production classification adds production challenge",
            expected_value="PRODUCTION",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_classified_production_target_when_resetting_then_production_challenge_is_required(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture(target_name="live")
    classified_analysis: CompileAnalysis = cast(
        CompileAnalysis,
        SimpleNamespace(
            realized_project=fixture.analysis.realized_project,
            graph=fixture.analysis.graph,
            compiled_project=SimpleNamespace(production_target=True),
        ),
    )

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="live",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=classified_analysis,
        connection=fixture.connection,
    )

    assert plan.challenges[-1] == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseDependencyFailureTestCase(
            description="unmanaged join reads an owned relation after its first source",
            expected_error_value="external_join_view",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unmanaged_join_dependant_when_planning_then_destruction_is_blocked(
    test_case: WarehouseDependencyFailureTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.catalog = replace(
        fixture.connection.catalog,
        relations=(
            *fixture.connection.catalog.relations,
            CatalogRelation(
                name="external_join_view",
                engine="View",
                columns=(),
                source_relation_names=("external_users", "tbl__orders"),
            ),
        ),
    )

    with pytest.raises(DestructionExternalDependencyError) as raised:
        plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="uat",
                database="analytics",
                metadata_database="metadata",
                pipeline_names=("alpha",),
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
            now=_NOW,
        )

    assert raised.value.relation_names == (test_case.expected_error_value,)


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseDependencyFailureTestCase(
            description="owned warehouse dependency graph contains a cycle",
            expected_error_value="dependency cycle",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_owned_relation_dependency_cycle_when_planning_then_plan_is_rejected(
    test_case: WarehouseDependencyFailureTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.catalog = replace(
        fixture.connection.catalog,
        relations=(
            *fixture.connection.catalog.relations,
            CatalogRelation(
                name="cycle_a",
                engine="View",
                columns=(),
                source_relation_names=("cycle_b",),
            ),
            CatalogRelation(
                name="cycle_b",
                engine="View",
                columns=(),
                source_relation_names=("cycle_a",),
            ),
        ),
    )
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=tuple(
            AdapterOwnedResourceEvent(
                event_id=f"owned-{name}",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name=name,
                resource_kind="view",
                pipeline_name="alpha",
                logical_resource_type="model",
                logical_resource_name=name,
                resource_role="historical_view",
                catalog_fingerprint=None,
            )
            for name in ("cycle_a", "cycle_b")
        ),
    )

    with pytest.raises(DestructionConsistencyError, match=test_case.expected_error_value):
        plan_destruction(
            request=DestructionRequest(
                operation="reset_target",
                target="uat",
                database="analytics",
                metadata_database="metadata",
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
            now=_NOW,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        StaleLedgerImpactTestCase(
            description="stale ledger identities extend reset impact and challenges",
            expected_pipeline_names=("alpha", "beta", "retired_pipeline"),
            expected_model_names=("orders", "retired_model", "summary"),
            expected_source_names=("events", "retired_source"),
            expected_challenges=("alpha", "beta", "retired_pipeline"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_attributable_stale_ledger_when_resetting_then_impact_and_challenges_include_it(
    test_case: StaleLedgerImpactTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=(
            AdapterOwnedResourceEvent(
                event_id="owned-retired-model",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name="retired_table",
                resource_kind="table",
                pipeline_name="retired_pipeline",
                logical_resource_type="model",
                logical_resource_name="retired_model",
                resource_role="model_table",
            ),
            AdapterOwnedResourceEvent(
                event_id="owned-retired-source",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name="retired_raw",
                resource_kind="table",
                pipeline_name="retired_pipeline",
                logical_resource_type="source",
                logical_resource_name="retired_source",
                resource_role="source_replay_table",
            ),
        ),
    )

    plan: DestructionPlan = plan_destruction(
        request=DestructionRequest(
            operation="reset_target",
            target="uat",
            database="analytics",
            metadata_database="metadata",
        ),
        analysis=fixture.analysis,
        connection=fixture.connection,
    )

    assert plan.affected_pipeline_names == test_case.expected_pipeline_names
    assert plan.affected_model_names == test_case.expected_model_names
    assert plan.affected_source_names == test_case.expected_source_names
    assert plan.challenges == test_case.expected_challenges


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="live pre-ledger manifest mismatch refuses bootstrap",
            expected_value="does not exactly match",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unowned_mismatched_manifest_relation_when_planning_then_bootstrap_is_refused(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.catalog_matches_resources = False

    with pytest.raises(DestructionResourceError, match=test_case.expected_value):
        plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="uat",
                database="analytics",
                metadata_database="metadata",
                pipeline_names=("alpha",),
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="reset without attributable pipeline remains fail closed",
            expected_value="attributable pipeline challenge",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_attributable_pipeline_when_building_challenges_then_reset_is_refused(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    with pytest.raises(DestructionSelectionError, match=test_case.expected_value):
        build_destruction_challenges(pipeline_names=())


@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipLedgerBehaviorTestCase(
            description="recorded pipeline identity constrains current manifest name",
            expected_value="tbl__orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_other_pipeline_binding_when_destroying_dependency_then_binding_blocks(
    test_case: OwnershipLedgerBehaviorTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    fixture.connection.owned_resources = AdapterOwnedResourceSnapshot(
        status="available",
        resources=(
            AdapterOwnedResourceEvent(
                event_id="owned-other-pipeline",
                event_type="owned",
                target_database="analytics",
                resource_database="analytics",
                resource_name=test_case.expected_value,
                resource_kind="view",
                pipeline_name="beta",
                logical_resource_type="model",
                logical_resource_name="orders",
                resource_role="stable_binding",
            ),
        ),
    )

    with pytest.raises(DestructionExternalDependencyError) as raised:
        plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="uat",
                database="analytics",
                metadata_database="metadata",
                pipeline_names=("alpha",),
            ),
            analysis=fixture.analysis,
            connection=fixture.connection,
        )

    assert raised.value.relation_names == (test_case.expected_value,)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
