"""Analyze model storage expressions against strict output columns."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import (
    generate_sql_tree,
    parse_sql_tree,
)
from streambuild.compiler.sql_analysis.constants import POLYGLOT_COLUMN_KEY, POLYGLOT_NAME_KEY
from streambuild.compiler.sql_analysis.exceptions import SqlStorageReferenceError
from streambuild.compiler.sql_analysis.models import SqlOutputColumn, SqlStorageExpression
from streambuild.compiler.sql_analysis.types import SqlStorageExpressionKind


def analyze_storage_expressions(
    *,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
    output_columns: tuple[SqlOutputColumn, ...],
    dialect: str,
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
            dialect=dialect,
        )
        for kind, expression in expressions
    )


def _analyze_storage_expression(
    *,
    kind: SqlStorageExpressionKind,
    expression: str,
    output_columns: tuple[SqlOutputColumn, ...],
    dialect: str,
) -> SqlStorageExpression:
    tree: dict[str, Any] = parse_sql_tree(sql=expression, dialect=dialect)
    referenced_column_names: tuple[str, ...] = tuple(_column_names(tree))
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
        canonical_sql=generate_sql_tree(tree=tree, dialect=dialect),
        referenced_column_names=referenced_column_names,
    )


def _column_names(node: Any) -> list[str]:
    names: list[str] = []
    if isinstance(node, list):
        item: Any
        for item in node:
            names.extend(_column_names(item))
        return names
    if not isinstance(node, dict):
        return names
    column_payload: Any = node.get(POLYGLOT_COLUMN_KEY)
    if isinstance(column_payload, dict):
        identifier: Any = column_payload.get(POLYGLOT_NAME_KEY)
        if isinstance(identifier, dict):
            name: Any = identifier.get(POLYGLOT_NAME_KEY)
            if isinstance(name, str):
                names.append(name)
        return names
    value: Any
    for value in node.values():
        if isinstance(value, dict | list):
            names.extend(_column_names(value))
    return names
