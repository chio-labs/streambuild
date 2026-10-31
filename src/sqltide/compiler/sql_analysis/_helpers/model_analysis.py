"""Assemble one strict immutable model SQL analysis result."""

import sqltide._native as _native
from sqltide.compiler.sql_analysis._helpers.aggregates import build_aggregate_facts
from sqltide.compiler.sql_analysis._helpers.polyglot import sql_tree_error
from sqltide.compiler.sql_analysis._helpers.scanning import extract_references_impl, scan_error
from sqltide.compiler.sql_analysis._helpers.storage import analyze_storage_expressions
from sqltide.compiler.sql_analysis.models import (
    SqlModelAnalysis,
    SqlOutputColumn,
    SqlProjection,
    SqlSourceSpan,
)
from sqltide.compiler.sql_analysis.types import SqlQueryShape


def analyze_model_sql_impl(
    *,
    sql: str,
    engine: str,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
    analyzer: _native.SqlTreeAnalyzer,
) -> tuple[SqlModelAnalysis, _native.SqlModelTree]:
    """Parse and derive all compiler-critical facts for one model."""

    try:
        tree: _native.SqlModelTree = analyzer.analyze_model(sql)
    except _native.SqlScanError as error:
        raise scan_error(error) from None
    except _native.SqlTreeError as error:
        raise sql_tree_error(error) from None
    projections: tuple[SqlProjection, ...] = tuple(
        SqlProjection(
            index=index,
            output=SqlOutputColumn(name=name, type=type_sql),
            span=SqlSourceSpan(*span),
        )
        for index, name, type_sql, span in tree.projections
    )
    analysis: SqlModelAnalysis = SqlModelAnalysis(
        authored_sql=sql,
        shape=SqlQueryShape.SELECT,
        projections=projections,
        references=extract_references_impl(sql),
        storage_expressions=analyze_storage_expressions(
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
            output_columns=tuple(projection.output for projection in projections),
            analyzer=analyzer,
        ),
        aggregate_facts=build_aggregate_facts(
            function_names=tree.function_names, has_group_by=tree.has_group_by, engine=engine
        ),
    )
    return analysis, tree
