"""Apache-2.0: SQLBuild compiler/graph/_helpers/lineage.py@7e3b2f854f05."""

from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    LogicalResourceKey,
    ParsedRef,
)
from streambuild.compiler.discovery.types import RefType
from streambuild.compiler.graph.exceptions import GraphInputError
from streambuild.compiler.graph.models import DependencyEdge
from streambuild.compiler.graph.types import DependencyEdgeType


def build_lineage_upstream_edges(
    *, project: CompiledProject
) -> dict[LogicalResourceKey, tuple[DependencyEdge, ...]]:
    """Build typed upstream edges for every logical source and model."""

    key_by_name: dict[str, LogicalResourceKey] = {
        resource.key.name: resource.key for resource in (*project.sources, *project.models)
    }
    upstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]] = {
        source.key: () for source in project.sources
    }
    model: CompiledModel
    for model in project.models:
        upstream_edges_by_key[model.key] = _model_upstream_edges(
            model=model,
            key_by_name=key_by_name,
        )
    return upstream_edges_by_key


def build_lineage_downstream_edges(
    *, upstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]]
) -> dict[LogicalResourceKey, tuple[DependencyEdge, ...]]:
    """Invert typed upstream edges while preserving deterministic ordering."""

    downstream_lists_by_key: dict[LogicalResourceKey, list[DependencyEdge]] = {
        key: [] for key in upstream_edges_by_key
    }
    edges: tuple[DependencyEdge, ...]
    for edges in upstream_edges_by_key.values():
        edge: DependencyEdge
        for edge in edges:
            downstream_lists_by_key.setdefault(edge.upstream_key, []).append(edge)
    return {
        key: tuple(sorted(edges, key=_downstream_edge_sort_key))
        for key, edges in downstream_lists_by_key.items()
    }


def _model_upstream_edges(
    *,
    model: CompiledModel,
    key_by_name: dict[str, LogicalResourceKey],
) -> tuple[DependencyEdge, ...]:
    edge_by_upstream_key: dict[LogicalResourceKey, DependencyEdge] = {}
    parsed_ref: ParsedRef
    for parsed_ref in model.parsed_refs:
        upstream_key: LogicalResourceKey | None = key_by_name.get(parsed_ref.name)
        if upstream_key is None:
            raise GraphInputError(
                f"Model '{model.key.name}' references unknown logical resource '{parsed_ref.name}'"
            )
        edge: DependencyEdge = DependencyEdge(
            upstream_key=upstream_key,
            downstream_key=model.key,
            edge_type=_edge_type(model=model, parsed_ref=parsed_ref),
        )
        existing_edge: DependencyEdge | None = edge_by_upstream_key.get(upstream_key)
        if existing_edge is not None and existing_edge.edge_type != edge.edge_type:
            raise GraphInputError(
                f"Model '{model.key.name}' declares conflicting reference types for "
                f"'{parsed_ref.name}'"
            )
        edge_by_upstream_key[upstream_key] = edge
    return tuple(sorted(edge_by_upstream_key.values(), key=_upstream_edge_sort_key))


def _edge_type(*, model: CompiledModel, parsed_ref: ParsedRef) -> DependencyEdgeType:
    if parsed_ref.name == model.transform.source:
        return DependencyEdgeType.DRIVING_INPUT
    if parsed_ref.ref_type == RefType.REFERENCE:
        return DependencyEdgeType.REFERENCE
    if parsed_ref.ref_type == RefType.MUTABLE:
        return DependencyEdgeType.MUTABLE_REFERENCE
    raise GraphInputError(
        f"Model '{model.key.name}' has an untyped side reference to '{parsed_ref.name}'"
    )


def _upstream_edge_sort_key(edge: DependencyEdge) -> tuple[str, str, str]:
    return (
        str(edge.upstream_key.resource_type),
        edge.upstream_key.name,
        str(edge.edge_type),
    )


def _downstream_edge_sort_key(edge: DependencyEdge) -> tuple[str, str, str]:
    return (
        str(edge.downstream_key.resource_type),
        edge.downstream_key.name,
        str(edge.edge_type),
    )
