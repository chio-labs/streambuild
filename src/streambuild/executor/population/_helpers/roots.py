"""Expand replay roots where direct catch-up prevents fan-in data loss."""

from dataclasses import replace

from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.executor.population.models import PopulationPlan, PopulationRoot


def expand_fan_in_roots(*, plan: PopulationPlan, desired_state: DesiredState) -> PopulationPlan:
    """Add direct catch-up roots for in-scope side-reference fan-in targets."""

    planned_keys: frozenset[ObjectKey] = frozenset(object_.logical_key for object_ in plan.objects)
    root_keys: set[ObjectKey] = {root.root_key for root in plan.roots}
    table_key_by_name: dict[str, ObjectKey] = {
        object_.name: object_.key
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
    }
    roots: list[PopulationRoot] = list(plan.roots)
    desired_object: DesiredMaterializedView | DesiredTable | object
    for desired_object in desired_state.objects:
        if (
            isinstance(desired_object, DesiredMaterializedView)
            and desired_object.key in planned_keys
        ):
            target_key: ObjectKey = table_key_by_name[desired_object.target_table_name]
            source_key: ObjectKey | None = table_key_by_name.get(desired_object.source_table_name)
            if source_key is None:
                continue
            side_keys: frozenset[ObjectKey] = frozenset(desired_object.deps) - {
                source_key,
                target_key,
            }
            if target_key not in root_keys and bool(side_keys & planned_keys):
                owner: PopulationRoot = next(
                    root for root in plan.roots if target_key in root.affected_keys
                )
                roots.append(
                    replace(
                        owner,
                        root_key=target_key,
                        affected_keys=(target_key, desired_object.key),
                        upstream_boundary_key=source_key,
                        persist_watermarks=False,
                    )
                )
                root_keys.add(target_key)
    return replace(plan, roots=tuple(roots))
