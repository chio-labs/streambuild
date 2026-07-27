"""Filtered traversal over immutable logical project graphs."""

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.graph.models import DependencyEdge, ProjectGraph
from streambuild.compiler.graph.types import DependencyEdgeType, GraphTraversalDirection


def collect_reachable_logical_keys(
    *,
    graph: ProjectGraph,
    root_keys: frozenset[LogicalResourceKey],
    direction: GraphTraversalDirection,
    edge_types: frozenset[DependencyEdgeType],
) -> tuple[LogicalResourceKey, ...]:
    """Collect roots and reachable keys through only the requested edge types."""

    visited_keys: set[LogicalResourceKey] = set(root_keys)
    stack: list[LogicalResourceKey] = list(reversed(graph.ordered_keys))
    stack = [key for key in stack if key in root_keys]
    while stack:
        current_key: LogicalResourceKey = stack.pop()
        edges: tuple[DependencyEdge, ...] = _edges_for_direction(
            graph=graph,
            key=current_key,
            direction=direction,
        )
        edge: DependencyEdge
        for edge in reversed(edges):
            if edge.edge_type not in edge_types:
                continue
            reachable_key: LogicalResourceKey = _reachable_key(edge=edge, direction=direction)
            if reachable_key in visited_keys:
                continue
            visited_keys.add(reachable_key)
            stack.append(reachable_key)
    return tuple(key for key in graph.ordered_keys if key in visited_keys)


def _edges_for_direction(
    *, graph: ProjectGraph, key: LogicalResourceKey, direction: GraphTraversalDirection
) -> tuple[DependencyEdge, ...]:
    if direction == GraphTraversalDirection.UPSTREAM:
        return graph.upstream_edges_by_key.get(key, ())
    return graph.downstream_edges_by_key.get(key, ())


def _reachable_key(
    *, edge: DependencyEdge, direction: GraphTraversalDirection
) -> LogicalResourceKey:
    if direction == GraphTraversalDirection.UPSTREAM:
        return edge.upstream_key
    return edge.downstream_key
