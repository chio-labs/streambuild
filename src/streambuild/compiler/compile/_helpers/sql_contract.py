"""Validate and derive the strict transform SQL output contract."""

from __future__ import annotations

from collections.abc import Sequence

from sqlglot import exp, parse, parse_one
from sqlglot.errors import ParseError

from streambuild.compiler.compile.exceptions import (
    TransformOrderByUnknownColumnError,
    TransformPartitionByUnknownColumnError,
    TransformSqlDuplicateAliasError,
    TransformSqlFinalQueryShapeError,
    TransformSqlMultipleStatementsError,
    TransformSqlParseError,
    TransformSqlStarProjectionError,
    TransformSqlTopLevelSetOperationError,
    TransformSqlUntypedProjectionError,
    TransformTtlUnknownColumnError,
)
from streambuild.compiler.shared.models import Column


def derive_transform_output_columns(*, transform_name: str, query: str) -> tuple[Column, ...]:
    """Validate transform SQL and derive output columns from the outermost SELECT."""

    statement: exp.Select = _parse_outermost_select(transform_name=transform_name, query=query)
    return _derive_select_columns(transform_name=transform_name, statement=statement)


def validate_order_by_expressions(
    *,
    transform_name: str,
    order_by: Sequence[str],
    available_columns: Sequence[Column],
) -> None:
    """Validate that ORDER BY expressions reference only derived output columns."""

    available_column_names: tuple[str, ...] = _available_column_names(available_columns)
    for expression in order_by:
        unknown_column_names: tuple[str, ...] = _unknown_output_columns(
            transform_name=transform_name,
            expression=expression,
            available_column_names=available_column_names,
        )
        if unknown_column_names:
            raise TransformOrderByUnknownColumnError(
                transform_name,
                expression,
                unknown_column_names,
                available_column_names,
            )


def validate_partition_by_expression(
    *,
    transform_name: str,
    partition_by: str | None,
    available_columns: Sequence[Column],
) -> None:
    """Validate that PARTITION BY references only derived output columns."""

    if partition_by is None:
        return

    available_column_names: tuple[str, ...] = _available_column_names(available_columns)
    unknown_column_names: tuple[str, ...] = _unknown_output_columns(
        transform_name=transform_name,
        expression=partition_by,
        available_column_names=available_column_names,
    )
    if unknown_column_names:
        raise TransformPartitionByUnknownColumnError(
            transform_name,
            partition_by,
            unknown_column_names,
            available_column_names,
        )


def validate_ttl_expression(
    *,
    transform_name: str,
    ttl: str | None,
    available_columns: Sequence[Column],
) -> None:
    """Validate that TTL references only derived output columns."""

    if ttl is None:
        return

    available_column_names: tuple[str, ...] = _available_column_names(available_columns)
    unknown_column_names: tuple[str, ...] = _unknown_output_columns(
        transform_name=transform_name, expression=ttl, available_column_names=available_column_names
    )
    if unknown_column_names:
        raise TransformTtlUnknownColumnError(
            transform_name,
            ttl,
            unknown_column_names,
            available_column_names,
        )


def _available_column_names(available_columns: Sequence[Column]) -> tuple[str, ...]:
    """Return the derived output column names in declaration order."""

    return tuple(column.name for column in available_columns)


def _unknown_output_columns(
    *,
    transform_name: str,
    expression: str,
    available_column_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return any output-column references not present in the derived schema."""

    available_column_name_set: set[str] = set(available_column_names)
    try:
        parsed_expression: exp.Expr = parse_one(expression, read="clickhouse")
    except ParseError as error:
        raise TransformSqlParseError(transform_name, expression, str(error)) from error

    referenced_column_names: tuple[str, ...] = tuple(
        column.name for column in parsed_expression.find_all(exp.Column)
    )
    return tuple(
        column_name
        for column_name in referenced_column_names
        if column_name not in available_column_name_set
    )


def _parse_outermost_select(*, transform_name: str, query: str) -> exp.Select:
    try:
        raw_statements: list[exp.Expr | None] = parse(query, read="clickhouse")
    except ParseError as error:
        raise TransformSqlParseError(
            transform_name=transform_name,
            query=query,
            details=str(error),
        ) from error

    statements: tuple[exp.Expr, ...] = tuple(
        statement for statement in raw_statements if statement is not None
    )
    if len(statements) != 1:
        raise TransformSqlMultipleStatementsError(
            transform_name=transform_name,
            statement_count=len(statements),
        )

    statement: exp.Expr = statements[0]
    if isinstance(statement, exp.SetOperation):
        raise TransformSqlTopLevelSetOperationError(
            transform_name=transform_name,
            statement_sql=statement.sql(dialect="clickhouse"),
        )
    if not isinstance(statement, exp.Select):
        raise TransformSqlFinalQueryShapeError(
            transform_name=transform_name,
            statement_type=statement.__class__.__name__,
        )
    return statement


def _derive_select_columns(*, transform_name: str, statement: exp.Select) -> tuple[Column, ...]:
    projections: tuple[exp.Expression, ...] = tuple(statement.expressions)
    derived_columns: list[Column] = []
    seen_aliases: set[str] = set()
    for column_index, projection in enumerate(projections, start=1):
        if isinstance(projection, exp.Star):
            raise TransformSqlStarProjectionError(
                transform_name=transform_name,
                column_index=column_index,
            )

        if not isinstance(projection, exp.Alias) or not isinstance(projection.this, exp.Cast):
            raise TransformSqlUntypedProjectionError(
                transform_name=transform_name,
                column_index=column_index,
                projection_sql=projection.sql(dialect="clickhouse"),
            )

        actual_alias: str = projection.alias
        if actual_alias in seen_aliases:
            raise TransformSqlDuplicateAliasError(
                transform_name=transform_name,
                alias=actual_alias,
            )
        seen_aliases.add(actual_alias)

        cast_expression: exp.Cast = projection.this
        derived_columns.append(
            Column(
                name=actual_alias,
                type=cast_expression.to.sql(dialect="clickhouse"),
            )
        )

    return tuple(derived_columns)
