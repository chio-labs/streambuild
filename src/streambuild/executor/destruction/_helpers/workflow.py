"""Dependency-safe destruction workflow assembly."""

from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnedResourceEvent
from streambuild.executor.destruction._helpers.ordering import (
    reverse_topologically_order_relations,
)
from streambuild.executor.destruction.models import DestructionPlan, DestructionRelationEvidence
from streambuild.executor.destruction.types import DestructionRelationKind
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_destruction_workflow(
    *, plan: DestructionPlan, connection: AdapterConnection | None = None
) -> tuple[WarehouseStatement, ...]:
    """Drop frozen owned relations in stable reverse-dependency order."""

    ordered: tuple[DestructionRelationEvidence, ...] = reverse_topologically_order_relations(
        plan.relations
    )
    statements: list[WarehouseStatement] = []
    if connection is not None:
        for index, sql in enumerate(
            connection.render_migrate_metadata_state(plan.metadata_database), start=1
        ):
            statements.append(
                WarehouseStatement(
                    sequence=len(statements) + 1,
                    step_id=f"migrate_ownership_metadata_{index:04d}",
                    phase=WorkflowPhase.PREPARATION,
                    intent=StatementIntent.MUTATION,
                    sql=sql,
                )
            )
    for relation_index, relation in enumerate(ordered, start=1):
        statements.append(
            WarehouseStatement(
                sequence=len(statements) + 1,
                step_id=f"destroy_relation_{relation_index:04d}",
                phase=WorkflowPhase.TEARDOWN,
                intent=StatementIntent.MUTATION,
                sql=(
                    f"DROP {_drop_sql_kind(DestructionRelationKind(relation.kind))} IF EXISTS "
                    f"{_quote_identifier(relation.database)}.{_quote_identifier(relation.name)} "
                    "SYNC;"
                ),
            )
        )
        if connection is None:
            continue
        event: AdapterOwnedResourceEvent = AdapterOwnedResourceEvent(
            event_id=f"dropped_{uuid4().hex}",
            event_type="dropped",
            target_database=plan.database,
            resource_database=relation.database,
            resource_name=relation.name,
            resource_kind=str(relation.kind),
            pipeline_name=relation.pipeline_names[0] if relation.pipeline_names else "",
            logical_resource_type=(
                "source"
                if set(relation.logical_names) & set(plan.affected_source_names)
                else "model"
            ),
            logical_resource_name=relation.logical_names[0] if relation.logical_names else "",
            resource_role="destruction_tombstone",
            catalog_fingerprint=relation.catalog_fingerprint,
        )
        for event_index, sql in enumerate(
            connection.render_owned_resource_events(
                database=plan.metadata_database,
                events=(event,),
            ),
            start=1,
        ):
            statements.append(
                WarehouseStatement(
                    sequence=len(statements) + 1,
                    step_id=(f"record_dropped_relation_{relation_index:04d}_{event_index:04d}"),
                    phase=WorkflowPhase.TEARDOWN,
                    intent=StatementIntent.MUTATION,
                    sql=sql,
                )
            )
    return tuple(statements)


def _drop_sql_kind(kind: DestructionRelationKind) -> str:
    if kind == DestructionRelationKind.VIEW:
        return "VIEW"
    return "TABLE"


def _quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"
