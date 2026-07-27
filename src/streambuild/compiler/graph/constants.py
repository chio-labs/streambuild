"""Dependency graph constants."""

from streambuild.compiler.graph.types import DependencyEdgeType

ALL_DEPENDENCY_EDGE_TYPES: frozenset[DependencyEdgeType] = frozenset(DependencyEdgeType)
DRIVING_DEPENDENCY_EDGE_TYPES: frozenset[DependencyEdgeType] = frozenset(
    {DependencyEdgeType.DRIVING_INPUT}
)
