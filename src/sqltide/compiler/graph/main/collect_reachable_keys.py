"""Collect a typed logical graph closure."""

from sqltide.compiler.compile.models import LogicalResourceKey
from sqltide.compiler.graph._helpers.traversal import collect_reachable_logical_keys
from sqltide.compiler.graph.models import ProjectGraph
from sqltide.compiler.graph.types import DependencyEdgeType, GraphTraversalDirection


def collect_reachable_keys(
    *,
    graph: ProjectGraph,
    root_keys: frozenset[LogicalResourceKey],
    direction: GraphTraversalDirection,
    edge_types: frozenset[DependencyEdgeType],
) -> tuple[LogicalResourceKey, ...]:
    """Return stable closure through only the selected semantic edge types."""

    return collect_reachable_logical_keys(
        graph=graph,
        root_keys=root_keys,
        direction=direction,
        edge_types=edge_types,
    )
