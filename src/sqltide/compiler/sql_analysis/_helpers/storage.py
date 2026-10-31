"""Analyze model storage expressions against strict output columns."""

import sqltide._native as _native
from sqltide.compiler.sql_analysis._helpers.polyglot import sql_tree_error
from sqltide.compiler.sql_analysis.exceptions import SqlStorageReferenceError
from sqltide.compiler.sql_analysis.models import SqlOutputColumn, SqlStorageExpression
from sqltide.compiler.sql_analysis.types import SqlStorageExpressionKind


def analyze_storage_expressions(
    *,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
    output_columns: tuple[SqlOutputColumn, ...],
    analyzer: _native.SqlTreeAnalyzer,
) -> tuple[SqlStorageExpression, ...]:
    """Parse every authored storage expression once and validate its references."""

    expressions: list[tuple[SqlStorageExpressionKind, str]] = [
        (SqlStorageExpressionKind.ORDER_BY, expression) for expression in order_by
    ]
    if partition_by is not None:
        expressions.append((SqlStorageExpressionKind.PARTITION_BY, partition_by))
    if ttl is not None:
        expressions.append((SqlStorageExpressionKind.TTL, ttl))
    return tuple(
        _analyze_storage_expression(
            kind=kind,
            expression=expression,
            output_columns=output_columns,
            analyzer=analyzer,
        )
        for kind, expression in expressions
    )


def _analyze_storage_expression(
    *,
    kind: SqlStorageExpressionKind,
    expression: str,
    output_columns: tuple[SqlOutputColumn, ...],
    analyzer: _native.SqlTreeAnalyzer,
) -> SqlStorageExpression:
    try:
        referenced_column_names: tuple[str, ...] = tuple(analyzer.storage_column_names(expression))
    except _native.SqlTreeError as error:
        raise sql_tree_error(error) from None
    available_column_names: tuple[str, ...] = tuple(column.name for column in output_columns)
    available: set[str] = set(available_column_names)
    unknown_column_names: tuple[str, ...] = tuple(
        name for name in referenced_column_names if name not in available
    )
    if unknown_column_names:
        raise SqlStorageReferenceError(
            kind=kind,
            expression=expression,
            unknown_column_names=unknown_column_names,
            available_column_names=available_column_names,
        )
    return SqlStorageExpression(
        kind=kind,
        sql=expression,
        referenced_column_names=referenced_column_names,
    )
