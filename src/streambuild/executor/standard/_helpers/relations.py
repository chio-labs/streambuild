"""Dependency-safe teardown and creation of directly named standard relations."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.planner.models import StandardPlan, StandardRelationOperation
from streambuild.executor.standard.constants import MODEL_TABLE_RELATION_INDEX


def drop_planned_relations(
    *, client: AdapterConnection, plan: StandardPlan, database: str
) -> tuple[str, ...]:
    """Drop every planned relation in the plan's reverse dependency order."""

    dropped: list[str] = []
    operation: StandardRelationOperation
    for operation in plan.teardown_operations:
        client.command(f"DROP TABLE IF EXISTS {database}.{operation.relation_name} SYNC")
        dropped.append(operation.relation_name)
    return tuple(dropped)


def target_relation_name_by_model_name(*, plan: StandardPlan) -> dict[str, str]:
    """Map every executed model to the directly named table replay writes into."""

    return {
        entry.model_key.name: entry.relation_names[MODEL_TABLE_RELATION_INDEX]
        for entry in plan.entries
    }
