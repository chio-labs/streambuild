"""Apache-2.0: SQLBuild compiler/graph/_helpers/lineage.py@7e3b2f854f05."""

from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledTableModel,
    CompiledViewModel,
    LogicalResourceKey,
    ParsedRef,
)
from streambuild.compiler.discovery.models import TransformStep, ViewStep
from streambuild.compiler.discovery.types import ModelReferenceScope, RefType
from streambuild.compiler.graph.exceptions import GraphInputError
from streambuild.compiler.graph.models import DependencyEdge
from streambuild.compiler.graph.types import DependencyEdgeType
from streambuild.compiler.sql_analysis.models import SqlSourceSpan
from streambuild.diagnostics.models import SourceLocation


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


def validate_terminal_views(
    *,
    project: CompiledProject,
    downstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]],
) -> None:
    """Reject every authored view that has a downstream logical model edge."""

    model: CompiledModel
    for model in project.models:
        if not isinstance(model, CompiledViewModel):
            continue
        downstream_edges: tuple[DependencyEdge, ...] = downstream_edges_by_key[model.key]
        if downstream_edges:
            downstream_names: str = ", ".join(edge.downstream_key.name for edge in downstream_edges)
            raise GraphInputError(
                f"View model '{model.key.name}' must be terminal; referenced by downstream "
                f"model(s): {downstream_names}"
            )


def validate_pipeline_mode_boundaries(
    *,
    project: CompiledProject,
    upstream_edges_by_key: dict[LogicalResourceKey, tuple[DependencyEdge, ...]],
) -> None:
    """Reject model relationships crossing direct and virtual pipelines."""

    model_by_key: dict[LogicalResourceKey, CompiledModel] = {
        model.key: model for model in project.models
    }
    mode_by_pipeline: dict[str, str] = {
        pipeline.pipeline.name: str(pipeline.pipeline.mode) for pipeline in project.pipelines
    }
    downstream_model: CompiledModel
    for downstream_model in project.models:
        edge: DependencyEdge
        for edge in upstream_edges_by_key[downstream_model.key]:
            upstream_model: CompiledModel | None = model_by_key.get(edge.upstream_key)
            if upstream_model is None:
                continue
            upstream_mode: str | None = mode_by_pipeline.get(upstream_model.pipeline_name)
            downstream_mode: str | None = mode_by_pipeline.get(downstream_model.pipeline_name)
            if upstream_mode is None or downstream_mode is None:
                continue
            if upstream_mode == downstream_mode:
                continue
            raise GraphInputError(
                f"Pipeline '{downstream_model.pipeline_name}' is {downstream_mode} but model "
                f"'{downstream_model.key.name}' references model '{upstream_model.key.name}' "
                f"in {upstream_mode} pipeline '{upstream_model.pipeline_name}'. Relations "
                "between direct and virtual pipelines are not allowed."
            )


def validate_model_reference_scope(*, project: CompiledProject) -> None:
    """Reject model edges crossing pipeline ownership when the project requires isolation."""

    if project.model_reference_scope == ModelReferenceScope.PROJECT:
        return
    model_by_name: dict[str, CompiledModel] = {model.key.name: model for model in project.models}
    downstream_model: CompiledModel
    for downstream_model in project.models:
        parsed_ref: ParsedRef
        for parsed_ref in downstream_model.parsed_refs:
            upstream_model: CompiledModel | None = model_by_name.get(parsed_ref.name)
            if (
                upstream_model is None
                or upstream_model.pipeline_name == downstream_model.pipeline_name
            ):
                continue
            raise GraphInputError(
                f"Model '{downstream_model.key.name}' in pipeline "
                f"'{downstream_model.pipeline_name}' references model "
                f"'{upstream_model.key.name}' in pipeline '{upstream_model.pipeline_name}', but "
                "dependencies.model_reference_scope is 'pipeline'.",
                location=_reference_location(model=downstream_model, parsed_ref=parsed_ref),
            )


def _reference_location(*, model: CompiledModel, parsed_ref: ParsedRef) -> SourceLocation | None:
    if isinstance(model, CompiledTableModel):
        step: TransformStep | ViewStep = model.transform
    elif isinstance(model, CompiledViewModel):
        step = model.view
    else:
        return None
    if step.source_file_path is None or parsed_ref.span is None:
        return None
    span: SqlSourceSpan = parsed_ref.span
    return SourceLocation(
        path=step.source_file_path,
        line=step.source_line + span.line - 1,
        column=(step.source_column + span.column - 1 if span.line == 1 else span.column),
        end_line=step.source_line + span.end_line - 1,
        end_column=(
            step.source_column + span.end_column - 1 if span.end_line == 1 else span.end_column
        ),
    )


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
    if isinstance(model, CompiledViewModel):
        return DependencyEdgeType.REFERENCE
    if not isinstance(model, CompiledTableModel):
        raise GraphInputError(f"Model '{model.key.name}' has an unsupported compiled kind")
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
