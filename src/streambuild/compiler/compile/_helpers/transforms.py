"""Transform compile helpers."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.compile._helpers.sql_contract import analyze_transform_model_sql
from streambuild.compiler.compile.constants import (
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import (
    Column,
    CompiledTableModel,
    CompiledViewModel,
    LogicalResourceKey,
    ParsedRef,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.constants import DEFAULT_SQL_MODEL_ENGINE
from streambuild.compiler.discovery.models import ReplayOnChangePolicy, TransformStep, ViewStep
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ModelKind,
    RefType,
    ReplayAnchorMode,
    ReplayLineageMode,
    SqlRelationType,
)
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.models import SqlModelAnalysis


def compile_model(
    *,
    transform: TransformStep,
    pipeline_dir: Path,
    pipeline_name: str,
    replay_lineage_mode: ReplayLineageMode,
    relation_name: str,
    bounded_replay_fallback: BoundedReplayFallback,
    sql_analyzer: SqlModelAnalyzer,
    replay_on_change: ReplayOnChangePolicy | None = None,
) -> CompiledTableModel:
    """Compile one authored transform into a logical model."""

    query: str = load_transform_query(transform=transform, pipeline_dir=pipeline_dir)
    sql_analysis: SqlModelAnalysis = analyze_transform_model_sql(
        analyzer=sql_analyzer,
        transform_name=transform.name,
        query=query,
        engine=transform.engine,
        order_by=tuple(transform.order_by),
        partition_by=transform.partition_by,
        ttl=transform.ttl,
    )
    if sql_analyzer.uses_prewhere(analysis=sql_analysis):
        raise PipelineCompileError(
            f"Transform '{transform.name}' uses PREWHERE, which ClickHouse does not allow in "
            "materialized views; use WHERE instead"
        )
    output_columns: tuple[Column, ...] = tuple(
        Column(name=column.name, type=column.type) for column in sql_analysis.output_columns
    )
    parsed_refs: tuple[ParsedRef, ...] = tuple(
        ParsedRef(
            name=reference.name,
            relation_type=reference.relation_type,
            ref_type=None if reference.ref_type is None else RefType(reference.ref_type),
            span=reference.span,
        )
        for reference in sql_analysis.references
    )
    validate_transform_refs(transform=transform, parsed_refs=parsed_refs)
    refs: tuple[str, ...] = tuple(parsed_ref.name for parsed_ref in parsed_refs)
    has_mutable_refs: bool = any(
        parsed_ref.relation_type == SqlRelationType.REF
        and parsed_ref.name != transform.source
        and parsed_ref.ref_type == RefType.MUTABLE
        for parsed_ref in parsed_refs
    )
    has_aggregate_semantics: bool = sql_analysis.aggregate_facts.has_semantics
    if transform.source not in refs:
        raise PipelineCompileError(
            f"Transform '{transform.name}' must reference its source '{transform.source}' in SQL"
        )

    preserves_required_lineage: bool = transform_preserves_required_lineage(
        output_columns=output_columns, replay_lineage_mode=replay_lineage_mode
    )
    replay_anchor_eligible: bool = build_replay_anchor_eligible(
        transform=transform,
        has_mutable_refs=has_mutable_refs,
        has_aggregate_semantics=has_aggregate_semantics,
        preserves_required_lineage=preserves_required_lineage,
    )
    return CompiledTableModel(
        key=LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name=transform.name),
        pipeline_name=pipeline_name,
        relation_name=relation_name,
        kind=ModelKind.TABLE,
        sql_analysis=sql_analysis,
        transform=transform,
        preserves_required_lineage=preserves_required_lineage,
        replay_anchor_eligible=replay_anchor_eligible,
        effective_bounded_replay_fallback=bounded_replay_fallback,
        replay_on_change=replay_on_change,
    )


def compile_view(
    *,
    view: ViewStep,
    pipeline_dir: Path,
    pipeline_name: str,
    relation_name: str,
    sql_analyzer: SqlModelAnalyzer,
) -> CompiledViewModel:
    """Compile one authored terminal view without table or replay semantics."""

    query: str = load_model_query(model=view, pipeline_dir=pipeline_dir)
    sql_analysis: SqlModelAnalysis = analyze_transform_model_sql(
        analyzer=sql_analyzer,
        transform_name=view.name,
        query=query,
        engine=DEFAULT_SQL_MODEL_ENGINE,
        order_by=(),
        partition_by=None,
        ttl=None,
    )
    parsed_refs: tuple[ParsedRef, ...] = tuple(
        ParsedRef(
            name=reference.name,
            relation_type=reference.relation_type,
            ref_type=None if reference.ref_type is None else RefType(reference.ref_type),
            span=reference.span,
        )
        for reference in sql_analysis.references
    )
    validate_view_refs(view=view, parsed_refs=parsed_refs)
    return CompiledViewModel(
        key=LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name=view.name),
        pipeline_name=pipeline_name,
        relation_name=relation_name,
        kind=ModelKind.VIEW,
        sql_analysis=sql_analysis,
        view=view,
    )


def load_transform_query(*, transform: TransformStep, pipeline_dir: Path) -> str:
    """Load a transform query from inline SQL or a relative file."""

    return load_model_query(model=transform, pipeline_dir=pipeline_dir)


def load_model_query(*, model: TransformStep | ViewStep, pipeline_dir: Path) -> str:
    """Load a table or view query from inline SQL or a relative file."""

    if model.query is not None:
        return model.query.strip()

    if model.sql_file is None:
        raise PipelineCompileError(
            f"Model '{model.name}' must define exactly one of 'query' or 'sql_file'"
        )
    sql_file_path: Path = (pipeline_dir / model.sql_file).resolve()
    return sql_file_path.read_text(encoding="utf-8").strip()


def validate_transform_refs(
    *, transform: TransformStep, parsed_refs: tuple[ParsedRef, ...]
) -> None:
    """Validate additional ref annotations for a transform query."""

    parsed_ref: ParsedRef
    for parsed_ref in parsed_refs:
        if parsed_ref.name == transform.source:
            if parsed_ref.ref_type is not None:
                raise PipelineCompileError(
                    f"Transform '{transform.name}' must not declare ref_type for its driving input "
                    f"'{transform.source}'"
                )
            continue
        if parsed_ref.ref_type is None:
            raise PipelineCompileError(
                f"Transform '{transform.name}' must declare ref_type for additional ref "
                f"'{parsed_ref.name}'"
            )
        if parsed_ref.relation_type != SqlRelationType.REF:
            raise PipelineCompileError(
                f"Transform '{transform.name}' must reference additional dependency "
                f"'{parsed_ref.name}' with __ref(...)"
            )


def validate_view_refs(*, view: ViewStep, parsed_refs: tuple[ParsedRef, ...]) -> None:
    """Reject table-only reference annotations on an ordinary view."""

    typed_ref_names: tuple[str, ...] = tuple(
        sorted({parsed_ref.name for parsed_ref in parsed_refs if parsed_ref.ref_type is not None})
    )
    if typed_ref_names:
        raise PipelineCompileError(
            f"View '{view.name}' must not declare ref_type annotations for: "
            f"{', '.join(typed_ref_names)}"
        )


def transform_preserves_required_lineage(
    *,
    output_columns: tuple[Column, ...],
    replay_lineage_mode: ReplayLineageMode,
) -> bool:
    """Return whether transform output preserves required replay-lineage columns."""

    output_column_names: set[str] = {column.name for column in output_columns}
    if replay_lineage_mode == ReplayLineageMode.LANDED_AT:
        return REPLAY_LANDED_AT_COLUMN_NAME in output_column_names

    required_column_names: set[str] = required_lineage_column_names(replay_lineage_mode)
    return required_column_names.issubset(output_column_names)


def required_lineage_column_names(replay_lineage_mode: ReplayLineageMode) -> set[str]:
    """Return the required output lineage column names for a replay mode."""

    if replay_lineage_mode == ReplayLineageMode.OFFSETS:
        return {REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME}
    if replay_lineage_mode == ReplayLineageMode.TIMESTAMP:
        return {REPLAY_TIMESTAMP_COLUMN_NAME}
    if replay_lineage_mode == ReplayLineageMode.CURSOR:
        return {REPLAY_CURSOR_COLUMN_NAME}
    return set()


def build_replay_anchor_eligible(
    *,
    transform: TransformStep,
    has_mutable_refs: bool,
    has_aggregate_semantics: bool,
    preserves_required_lineage: bool,
) -> bool:
    """Return whether a compiled transform output is replay-anchor-eligible."""

    if transform.replay_anchor == ReplayAnchorMode.NEVER:
        return False
    if has_mutable_refs:
        return False
    if has_aggregate_semantics:
        return False
    if not preserves_required_lineage:
        return False
    return True
