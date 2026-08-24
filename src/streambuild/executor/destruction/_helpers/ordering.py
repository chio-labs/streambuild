"""Deterministic dependency ordering for destructive relation groups."""

from heapq import heappop, heappush

from streambuild.executor.destruction.exceptions import DestructionConsistencyError
from streambuild.executor.destruction.models import DestructionRelationEvidence


def reverse_topologically_order_relations(
    relations: tuple[DestructionRelationEvidence, ...],
) -> tuple[DestructionRelationEvidence, ...]:
    """Order dependants before prerequisites with deterministic lexical ties."""

    by_name: dict[str, DestructionRelationEvidence] = {}
    for relation in relations:
        if relation.name in by_name:
            raise DestructionConsistencyError(
                f"Destruction evidence contains duplicate relation {relation.name!r}"
            )
        by_name[relation.name] = relation
    dependencies_by_name: dict[str, tuple[str, ...]] = {
        name: tuple(sorted(set(relation.dependency_relation_names) & by_name.keys()))
        for name, relation in by_name.items()
    }
    dependant_counts: dict[str, int] = dict.fromkeys(by_name, 0)
    for dependencies in dependencies_by_name.values():
        for dependency in dependencies:
            dependant_counts[dependency] += 1

    ready: list[str] = [name for name, count in dependant_counts.items() if count == 0]
    ready.sort()
    ordered: list[DestructionRelationEvidence] = []
    while ready:
        name: str = heappop(ready)
        ordered.append(by_name[name])
        for dependency in dependencies_by_name[name]:
            dependant_counts[dependency] -= 1
            if dependant_counts[dependency] == 0:
                heappush(ready, dependency)

    if len(ordered) != len(relations):
        unresolved: tuple[str, ...] = tuple(
            sorted(name for name, count in dependant_counts.items() if count > 0)
        )
        raise DestructionConsistencyError(
            f"Destruction relation dependency cycle blocks ordering: {unresolved!r}"
        )
    return tuple(ordered)
