"""Dependency-safe teardown and creation of directly named direct relations."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.planner.models import DirectPlan, DirectPlanEntry, DirectRelationOperation
from streambuild.compiler.planner.types import DirectResourceKind


def drop_planned_relations(
    *, client: AdapterConnection, plan: DirectPlan, database: str
) -> tuple[str, ...]:
    """Drop every planned relation in the plan's reverse dependency order."""

    dropped: list[str] = []
    operation: DirectRelationOperation
    for operation in plan.teardown_operations:
        relation_type: str = (
            "VIEW" if operation.resource_kind == DirectResourceKind.VIEW else "TABLE"
        )
        client.command(f"DROP {relation_type} IF EXISTS {database}.{operation.relation_name} SYNC")
        dropped.append(operation.relation_name)
    return tuple(dropped)


def target_relation_name_by_model_name(*, plan: DirectPlan) -> dict[str, str]:
    """Map every executed model to the directly named table replay writes into."""

    target_names: dict[str, str] = {}
    entry: DirectPlanEntry
    for entry in plan.entries:
        relation_name: str
        resource_kind: DirectResourceKind
        for relation_name, resource_kind in zip(
            entry.relation_names, entry.resource_kinds, strict=True
        ):
            if resource_kind == DirectResourceKind.TABLE:
                target_names[entry.model_key.name] = relation_name
    return target_names
