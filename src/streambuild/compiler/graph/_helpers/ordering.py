"""Apache-2.0: SQLBuild compiler/planner/_helpers/graph/core.py@7e3b2f854f05."""

from collections.abc import Mapping

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.graph.exceptions import GraphInputError
from streambuild.compiler.graph.models import DependencyEdge


def topologically_order_logical_keys(
    *,
    upstream_edges_by_key: Mapping[LogicalResourceKey, tuple[DependencyEdge, ...]],
    downstream_edges_by_key: Mapping[LogicalResourceKey, tuple[DependencyEdge, ...]],
) -> tuple[LogicalResourceKey, ...]:
    """Return every logical key in stable dependency order or reject a cycle."""

    indegree_by_key: dict[LogicalResourceKey, int] = {
        key: len(edges) for key, edges in upstream_edges_by_key.items()
    }
    ready_keys: list[LogicalResourceKey] = sorted(
        (key for key, indegree in indegree_by_key.items() if indegree == 0),
        key=_logical_key_sort_key,
    )
    ordered_keys: list[LogicalResourceKey] = []
    while ready_keys:
        current_key: LogicalResourceKey = ready_keys.pop(0)
        ordered_keys.append(current_key)
        edge: DependencyEdge
        for edge in downstream_edges_by_key.get(current_key, ()):
            downstream_key: LogicalResourceKey = edge.downstream_key
            indegree_by_key[downstream_key] -= 1
            if indegree_by_key[downstream_key] == 0:
                ready_keys.append(downstream_key)
                ready_keys.sort(key=_logical_key_sort_key)
    if len(ordered_keys) != len(indegree_by_key):
        unresolved_keys: tuple[LogicalResourceKey, ...] = tuple(
            sorted(
                (key for key in indegree_by_key if key not in ordered_keys),
                key=_logical_key_sort_key,
            )
        )
        unresolved_names: str = ", ".join(
            f"{key.resource_type}:{key.name}" for key in unresolved_keys
        )
        raise GraphInputError(f"Dependency cycle detected involving: {unresolved_names}")
    return tuple(ordered_keys)


def _logical_key_sort_key(key: LogicalResourceKey) -> tuple[str, str]:
    return (str(key.resource_type), key.name)
