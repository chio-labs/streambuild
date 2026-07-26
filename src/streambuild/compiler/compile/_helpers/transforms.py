"""Transform compile helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlglot import exp, parse_one

from streambuild.compiler.compile._helpers.naming import raw_table_name, transform_mv_name
from streambuild.compiler.compile._helpers.sql_contract import (
    derive_transform_output_columns,
    validate_order_by_expressions,
    validate_partition_by_expression,
    validate_ttl_expression,
)
from streambuild.compiler.compile.constants import (
    AGGREGATING_ENGINE_NAMES,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
    REPLAY_CURSOR_COLUMN_NAME,
    REPLAY_LANDED_AT_COLUMN_NAME,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
    REPLAY_TIMESTAMP_COLUMN_NAME,
)
from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.main._extract_refs import extract_refs
from streambuild.compiler.compile.main.replace_refs import replace_refs
from streambuild.compiler.compile.main.transform_table_name import transform_table_name
from streambuild.compiler.compile.models import (
    Column,
    CompiledTransformStep,
    DesiredMaterializedView,
    DesiredTable,
    MaterializedViewSpec,
    ObjectKey,
    ParsedRef,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.discovery.models import ExternalTableSourceStep, Pipeline, TransformStep
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    RefType,
    ReplayAnchorMode,
    ReplayLineageMode,
    SqlRelationType,
)


def compile_transform(
    *,
    transform: TransformStep,
    pipeline_file_path: Path,
    relation_names: dict[str, str],
    relation_sqls: dict[str, str],
    replay_lineage_mode: ReplayLineageMode,
    bounded_replay_fallback: BoundedReplayFallback,
) -> CompiledTransformStep:
    """Compile a transform step into desired objects."""

    query: str = load_transform_query(transform=transform, pipeline_file_path=pipeline_file_path)
    output_columns: tuple[Column, ...] = derive_transform_output_columns(
        transform_name=transform.name, query=query
    )
    validate_order_by_expressions(
        transform_name=transform.name, order_by=transform.order_by, available_columns=output_columns
    )
    validate_partition_by_expression(
        transform_name=transform.name,
        partition_by=transform.partition_by,
        available_columns=output_columns,
    )
    validate_ttl_expression(
        transform_name=transform.name, ttl=transform.ttl, available_columns=output_columns
    )
    parsed_refs: tuple[ParsedRef, ...] = tuple(extract_refs(query))
    validate_transform_refs(transform=transform, parsed_refs=parsed_refs)
    refs: tuple[str, ...] = tuple(parsed_ref.name for parsed_ref in parsed_refs)
    has_mutable_refs: bool = any(
        parsed_ref.relation_type == SqlRelationType.REF
        and parsed_ref.name != transform.source
        and parsed_ref.ref_type == RefType.MUTABLE
        for parsed_ref in parsed_refs
    )
    has_aggregate_semantics: bool = transform_has_aggregate_semantics(
        transform=transform, query=query
    )
    if transform.source not in refs:
        raise PipelineCompileError(
            f"Transform '{transform.name}' must reference its source '{transform.source}' in SQL"
        )

    resolved_query: str = replace_refs(sql=query, resolver=relation_sqls)
    output_columns: tuple[Column, ...] = derive_transform_output_columns(
        transform_name=transform.name, query=resolved_query
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
    target_table_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_TABLE,
        name=transform_table_name(transform.name),
    )
    source_table_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_TABLE,
        name=relation_names[transform.source],
    )
    dependency_table_keys: tuple[ObjectKey, ...] = tuple(
        dict.fromkeys(
            ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_TABLE,
                name=relation_names[parsed_ref.name],
            )
            for parsed_ref in parsed_refs
        )
    )
    materialized_view_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
        name=transform_mv_name(transform.name),
    )
    return CompiledTransformStep(
        transform=transform,
        parsed_refs=parsed_refs,
        resolved_query=resolved_query,
        refs=refs,
        has_mutable_refs=has_mutable_refs,
        has_aggregate_semantics=has_aggregate_semantics,
        preserves_required_lineage=preserves_required_lineage,
        replay_anchor_eligible=replay_anchor_eligible,
        effective_bounded_replay_fallback=bounded_replay_fallback,
        target_table=compile_transform_table(
            transform=transform,
            output_columns=output_columns,
            key=target_table_key,
            source_table_key=source_table_key,
            bounded_replay_fallback=bounded_replay_fallback,
        ),
        materialized_view=DesiredMaterializedView(
            key=materialized_view_key,
            deps=(*dependency_table_keys, target_table_key),
            spec=MaterializedViewSpec(
                source_table_name=relation_names[transform.source],
                target_table_name=transform_table_name(transform.name),
                query=resolved_query,
            ),
        ),
        target_table_name=transform_table_name(transform.name),
    )


def relation_names_for_pipeline(pipeline: Pipeline) -> dict[str, str]:
    """Build the logical-to-physical relation name map for a pipeline."""

    relation_names: dict[str, str]
    if isinstance(pipeline.source, ExternalTableSourceStep):
        relation_names = {pipeline.source.name: pipeline.source.table_name}
    else:
        relation_names = {pipeline.source.name: raw_table_name(pipeline.source.name)}
    for transform in pipeline.transforms:
        relation_names[transform.name] = transform_table_name(transform.name)
    return relation_names


def relation_sqls_for_pipeline(pipeline: Pipeline) -> dict[str, str]:
    """Build the logical-to-SQL relation surface map for a pipeline."""

    relation_sqls: dict[str, str] = relation_names_for_pipeline(pipeline)
    if isinstance(pipeline.source, ExternalTableSourceStep):
        relation_sqls[pipeline.source.name] = _external_source_relation_sql(pipeline.source)
    return relation_sqls


def load_transform_query(*, transform: TransformStep, pipeline_file_path: Path) -> str:
    """Load a transform query from inline SQL or a relative file."""

    if transform.query is not None:
        return transform.query.strip()

    if transform.sql_file is None:
        raise PipelineCompileError(
            f"Transform '{transform.name}' must define exactly one of 'query' or 'sql_file'"
        )
    sql_file_path: Path = (pipeline_file_path.parent / transform.sql_file).resolve()
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


def transform_has_aggregate_semantics(*, transform: TransformStep, query: str) -> bool:
    """Return whether a transform is conservatively aggregate/stateful."""

    engine_name: str = transform.engine.lower()
    if any(name in engine_name for name in AGGREGATING_ENGINE_NAMES):
        return True

    return _query_has_aggregate_semantics(query)


@lru_cache(maxsize=256)
def _query_has_aggregate_semantics(query: str) -> bool:
    expression: exp.Expr = parse_one(query, dialect="clickhouse")
    if expression.find(exp.Group) is not None:
        return True

    aggregate_function: exp.AggFunc | None = expression.find(exp.AggFunc)
    return aggregate_function is not None


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


def _external_source_relation_sql(source: ExternalTableSourceStep) -> str:
    alias_expressions: list[str] = []
    if source.replay_boundary.columns.partition is not None:
        alias_expressions.append(
            f"{source.replay_boundary.columns.partition} AS {REPLAY_PARTITION_COLUMN_NAME}"
        )
    if source.replay_boundary.columns.offset is not None:
        alias_expressions.append(
            f"{source.replay_boundary.columns.offset} AS {REPLAY_OFFSET_COLUMN_NAME}"
        )
    if source.replay_boundary.columns.timestamp is not None:
        alias_expressions.append(
            f"{source.replay_boundary.columns.timestamp} AS {REPLAY_TIMESTAMP_COLUMN_NAME}"
        )
    if source.replay_boundary.columns.landed_at is not None:
        alias_expressions.append(
            f"{source.replay_boundary.columns.landed_at} AS {REPLAY_LANDED_AT_COLUMN_NAME}"
        )
    if source.replay_boundary.columns.cursor is not None:
        alias_expressions.append(
            f"{source.replay_boundary.columns.cursor} AS {REPLAY_CURSOR_COLUMN_NAME}"
        )
    if not alias_expressions:
        return source.table_name
    alias_projection_sql: str = ",\n    ".join(alias_expressions)
    return f"(SELECT\n    *,\n    {alias_projection_sql}\nFROM {source.table_name})"


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


def compile_transform_table(
    *,
    transform: TransformStep,
    output_columns: tuple[Column, ...],
    key: ObjectKey,
    source_table_key: ObjectKey,
    bounded_replay_fallback: BoundedReplayFallback | str,
) -> DesiredTable:
    """Compile the managed target table for a transform."""

    return DesiredTable(
        key=key,
        deps=(source_table_key,),
        spec=TableSpec(
            columns=output_columns,
            storage=TableStorage(
                engine=transform.engine,
                order_by=tuple(transform.order_by),
                partition_by=transform.partition_by,
                ttl=transform.ttl,
                settings=transform.settings,
            ),
        ),
        schema_change_backfill=transform.schema_change_backfill,
        bounded_replay_fallback=BoundedReplayFallback(bounded_replay_fallback),
    )
