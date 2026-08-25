"""Dependency-safe destruction workflow assembly."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
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

    ordered: tuple[DestructionRelationEvidence, ...] = tuple(
        relation
        for relation in reverse_topologically_order_relations(plan.relations)
        if relation.exists
    )
    statements: list[WarehouseStatement] = []
    for relation_index, relation in enumerate(ordered, start=1):
        statements.append(
            WarehouseStatement(
                sequence=len(statements) + 1,
                step_id=f"destroy_relation_{relation_index:04d}",
                phase=WorkflowPhase.TEARDOWN,
                intent=StatementIntent.MUTATION,
                display_name=(
                    f"Drop {_drop_sql_kind(DestructionRelationKind(relation.kind)).lower()} "
                    f"{relation.database}.{relation.name}"
                ),
                sql=(
                    f"DROP {_drop_sql_kind(DestructionRelationKind(relation.kind))} IF EXISTS "
                    f"{_quote_identifier(relation.database)}.{_quote_identifier(relation.name)} "
                    f"SYNC{_drop_settings(plan=plan)};"
                ),
            )
        )
    return tuple(statements)


def _drop_sql_kind(kind: DestructionRelationKind) -> str:
    if kind == DestructionRelationKind.VIEW:
        return "VIEW"
    return "TABLE"


def _quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def _drop_settings(*, plan: DestructionPlan) -> str:
    limit: int | None = plan.relation_drop_size_override
    if limit is None:
        return ""
    return f" SETTINGS max_table_size_to_drop = {limit}"
