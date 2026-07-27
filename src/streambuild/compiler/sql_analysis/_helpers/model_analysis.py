"""Assemble one strict immutable model SQL analysis result."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.aggregates import aggregate_facts
from streambuild.compiler.sql_analysis._helpers.polyglot import (
    analyze_query_facts,
    generate_sql_tree,
    parse_sql_trees,
)
from streambuild.compiler.sql_analysis._helpers.projection_spans import outer_projection_spans
from streambuild.compiler.sql_analysis._helpers.projections import build_model_projections
from streambuild.compiler.sql_analysis._helpers.scanning import extract_references_impl
from streambuild.compiler.sql_analysis._helpers.storage import analyze_storage_expressions
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_EXCEPT_KEY,
    POLYGLOT_INTERSECT_KEY,
    POLYGLOT_SELECT_KEY,
    POLYGLOT_UNION_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import (
    SqlQueryShapeError,
    SqlStatementCountError,
)
from streambuild.compiler.sql_analysis.models import SqlModelAnalysis, SqlProjection
from streambuild.compiler.sql_analysis.types import SqlQueryShape

_SET_OPERATION_KEYS: frozenset[str] = frozenset(
    {POLYGLOT_UNION_KEY, POLYGLOT_INTERSECT_KEY, POLYGLOT_EXCEPT_KEY}
)


def analyze_model_sql_impl(
    *,
    sql: str,
    engine: str,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
    dialect: str,
) -> tuple[SqlModelAnalysis, dict[str, Any]]:
    """Parse and derive all compiler-critical facts for one model."""

    trees: tuple[dict[str, Any], ...] = parse_sql_trees(sql=sql, dialect=dialect)
    if len(trees) != 1:
        raise SqlStatementCountError(len(trees))
    tree: dict[str, Any] = trees[0]
    statement_type: str = next(iter(tree), "unknown")
    select_payload: Any = tree.get(POLYGLOT_SELECT_KEY)
    if not isinstance(select_payload, dict):
        canonical_sql: str = generate_sql_tree(tree=tree, dialect=dialect, pretty=True)
        raise SqlQueryShapeError(
            statement_type=statement_type,
            statement_sql=canonical_sql,
            is_set_operation=statement_type in _SET_OPERATION_KEYS,
        )
    compact_analysis: dict[str, Any] = analyze_query_facts(sql=sql, dialect=dialect)
    projections: tuple[SqlProjection, ...] = build_model_projections(
        select_payload=select_payload,
        sql=sql,
        spans=outer_projection_spans(sql),
        compact_analysis=compact_analysis,
        dialect=dialect,
    )
    canonical_sql = generate_sql_tree(tree=tree, dialect=dialect, pretty=True)
    analysis: SqlModelAnalysis = SqlModelAnalysis(
        authored_sql=sql,
        canonical_sql=canonical_sql,
        shape=SqlQueryShape.SELECT,
        projections=projections,
        references=extract_references_impl(sql),
        storage_expressions=analyze_storage_expressions(
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
            output_columns=tuple(projection.output for projection in projections),
            dialect=dialect,
        ),
        aggregate_facts=aggregate_facts(tree=tree, engine=engine),
    )
    return analysis, tree
