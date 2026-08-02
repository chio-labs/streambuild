"""Dependency-safe teardown and creation of directly named direct relations."""

from streambuild.compiler.planner.models import DirectPlan, DirectPlanEntry
from streambuild.compiler.planner.types import DirectResourceKind


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
