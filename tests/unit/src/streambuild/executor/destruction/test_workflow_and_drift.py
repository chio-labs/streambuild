from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnedResourceEvent, CatalogRelation
from streambuild.executor.destruction.exceptions import DestructionDriftError
from streambuild.executor.destruction.main.assemble_destruction_workflow import (
    assemble_destruction_workflow,
)
from streambuild.executor.destruction.main.plan_destruction import plan_destruction
from streambuild.executor.destruction.main.verify_destruction_drift import (
    verify_destruction_drift,
)
from streambuild.executor.destruction.models import (
    DestructionPlan,
    DestructionRelationEvidence,
    DestructionRequest,
)
from streambuild.executor.workflow.models import WarehouseStatement
from tests.unit.src.streambuild.executor.destruction._test_types import (
    DestructionWorkflowTestCase,
    DeterministicDestructionOrderTestCase,
    EquivalentDriftTestCase,
    RejectedDriftTestCase,
    TombstoneAdjacencyTestCase,
)
from tests.unit.src.streambuild.executor.destruction.helpers import (
    PlanningFixture,
    build_planning_fixture,
)

_NOW: datetime = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


class TombstoneRenderingConnection:
    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        del database
        return ()

    def render_owned_resource_events(
        self, *, database: str, events: tuple[AdapterOwnedResourceEvent, ...]
    ) -> tuple[str, ...]:
        del database
        return (f"TOMBSTONE {events[0].resource_name};",)


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionWorkflowTestCase(
            description="mixed owned relations are dropped in dependency safe order",
            expected_first_sql="DROP TABLE IF EXISTS `analytics`.`mv__events` SYNC;",
            expected_sql_suffix=" SYNC;",
            expected_view_sql="DROP VIEW IF EXISTS `analytics`.`vw__summary` SYNC;",
            expected_table_sql="DROP VIEW IF EXISTS `analytics`.`tbl__orders` SYNC;",
            expected_has_relation_kinds=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_owned_relations_when_assembling_workflow_then_order_is_dependency_safe(
    test_case: DestructionWorkflowTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    relations_by_name: dict[str, CatalogRelation] = {
        relation.name: relation for relation in fixture.connection.catalog.relations
    }
    relations_by_name["vw__summary"] = replace(
        relations_by_name["vw__summary"], source_relation_names=("tbl__orders",)
    )
    fixture.connection.catalog = replace(
        fixture.connection.catalog,
        relations=tuple(relations_by_name[name] for name in relations_by_name),
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
        now=_NOW,
    )

    statements: tuple[WarehouseStatement, ...] = assemble_destruction_workflow(plan=plan)
    sql: tuple[str, ...] = tuple(statement.sql for statement in statements)
    kinds: tuple[object, ...] = tuple(relation.kind for relation in plan.relations)

    assert sql[0] == test_case.expected_first_sql
    assert all(statement.sequence == index for index, statement in enumerate(statements, start=1))
    assert all(statement.sql.endswith(test_case.expected_sql_suffix) for statement in statements)
    assert bool(kinds) is test_case.expected_has_relation_kinds
    assert sql.index(test_case.expected_view_sql) < sql.index(test_case.expected_table_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        DeterministicDestructionOrderTestCase(
            description="equivalent graphs have stable lexical tie ordering",
            expected_orders_equal=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equivalent_dependency_graphs_when_ordering_then_input_order_does_not_matter(
    test_case: DeterministicDestructionOrderTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    plan: DestructionPlan = plan_destruction(
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

    first: tuple[str, ...] = tuple(
        statement.sql for statement in assemble_destruction_workflow(plan=plan)
    )
    second: tuple[str, ...] = tuple(
        statement.sql
        for statement in assemble_destruction_workflow(
            plan=replace(plan, relations=tuple(reversed(plan.relations)))
        )
    )

    assert (second == first) is test_case.expected_orders_equal


@pytest.mark.parametrize(
    "test_case",
    [
        TombstoneAdjacencyTestCase(
            description="each drop is immediately followed by its ownership tombstone",
            expected_statement_multiplier=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_owned_relations_when_rendering_then_each_tombstone_follows_its_drop(
    test_case: TombstoneAdjacencyTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
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

    statements: tuple[WarehouseStatement, ...] = assemble_destruction_workflow(
        plan=plan,
        connection=cast(AdapterConnection, TombstoneRenderingConnection()),
    )

    assert len(statements) == len(plan.relations) * test_case.expected_statement_multiplier
    for index in range(0, len(statements), 2):
        drop: WarehouseStatement = statements[index]
        tombstone: WarehouseStatement = statements[index + 1]
        assert drop.sql.startswith("DROP ")
        assert tombstone.sql == f"TOMBSTONE {drop.sql.split('`.`', 1)[1].split('`', 1)[0]};"
        assert tombstone.step_id.startswith("record_dropped_relation_")


@pytest.mark.parametrize(
    "test_case",
    [
        EquivalentDriftTestCase(
            description="an equivalent fresh plan is returned after drift verification",
            expected_plan_id="fresh",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_equivalent_fresh_plan_when_verifying_drift_then_fresh_plan_is_returned(
    test_case: EquivalentDriftTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    request: DestructionRequest = DestructionRequest(
        operation="destroy_pipelines",
        target="uat",
        database="analytics",
        metadata_database="metadata",
        pipeline_names=("alpha",),
    )
    frozen: DestructionPlan = plan_destruction(
        request=request,
        analysis=fixture.analysis,
        connection=fixture.connection,
        now=_NOW,
    )
    fresh: DestructionPlan = replace(
        frozen,
        plan_id=test_case.expected_plan_id,
        created_at=_NOW,
        expires_at=frozen.expires_at,
    )

    result: DestructionPlan = verify_destruction_drift(frozen_plan=frozen, replan=lambda: fresh)

    assert result.plan_id == test_case.expected_plan_id
    assert result is fresh


@pytest.mark.parametrize(
    "test_case",
    [
        RejectedDriftTestCase(
            description="changed warehouse evidence rejects execution",
            expected_error_match="impact",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_warehouse_evidence_when_verifying_drift_then_execution_is_rejected(
    test_case: RejectedDriftTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    frozen: DestructionPlan = plan_destruction(
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
    changed_relation: DestructionRelationEvidence = replace(
        frozen.relations[0], exists=not frozen.relations[0].exists
    )
    changed: DestructionPlan = replace(
        frozen,
        plan_fingerprint="0" * 64,
        relations=(changed_relation, *frozen.relations[1:]),
    )

    with pytest.raises(DestructionDriftError, match=test_case.expected_error_match):
        verify_destruction_drift(frozen_plan=frozen, replan=lambda: changed)


@pytest.mark.parametrize(
    "test_case",
    [
        RejectedDriftTestCase(
            description="changed manifest takes precedence over impact drift",
            expected_error_match="manifest",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_manifest_when_verifying_drift_then_manifest_error_takes_precedence(
    test_case: RejectedDriftTestCase,
) -> None:
    fixture: PlanningFixture = build_planning_fixture()
    frozen: DestructionPlan = plan_destruction(
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
    changed: DestructionPlan = replace(
        frozen, manifest_fingerprint="f" * 64, plan_fingerprint="e" * 64
    )

    with pytest.raises(DestructionDriftError, match=test_case.expected_error_match):
        verify_destruction_drift(frozen_plan=frozen, replan=lambda: changed)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
