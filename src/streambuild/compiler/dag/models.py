"""Immutable logical DAG artifact models."""

from dataclasses import dataclass

from streambuild.compiler.dag.types import DagNodeType


@dataclass(frozen=True)
class DagNode:
    """One logical resource or check node."""

    id: str
    node_type: DagNodeType
    name: str


@dataclass(frozen=True)
class DagEdge:
    """One typed upstream-to-downstream DAG edge."""

    from_id: str
    to_id: str
    edge_type: str


@dataclass(frozen=True)
class DagArtifact:
    """One deterministic StreamBuild-native logical DAG."""

    nodes: tuple[DagNode, ...]
    edges: tuple[DagEdge, ...]
    macro_names: tuple[str, ...]
