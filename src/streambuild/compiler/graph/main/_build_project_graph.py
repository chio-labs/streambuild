"""Build one typed graph from a compiled logical project."""

from streambuild.compiler.compile.models import CompiledProject, LogicalResourceKey
from streambuild.compiler.graph._helpers.lineage import (
    build_lineage_downstream_edges,
    build_lineage_upstream_edges,
)
from streambuild.compiler.graph._helpers.ordering import topologically_order_logical_keys
from streambuild.compiler.graph.models import DependencyEdge, ProjectGraph


def build_project_graph_from_compiled_project(*, project: CompiledProject) -> ProjectGraph:
    """Build and validate one immutable typed logical graph."""

    upstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]] = (
        build_lineage_upstream_edges(project=project)
    )
    downstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]] = (
        build_lineage_downstream_edges(upstream_edges_by_key=upstream_edges_by_key)
    )
    return ProjectGraph(
        project=project,
        upstream_edges_by_key=upstream_edges_by_key,
        downstream_edges_by_key=downstream_edges_by_key,
        ordered_keys=topologically_order_logical_keys(
            upstream_edges_by_key=upstream_edges_by_key,
            downstream_edges_by_key=downstream_edges_by_key,
        ),
    )
