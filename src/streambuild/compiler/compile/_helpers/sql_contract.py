"""Adapt strict SQL-analysis failures and facts to compile contracts."""

from collections.abc import Sequence

from streambuild.compiler.compile.exceptions import (
    TransformOrderByUnknownColumnError,
    TransformPartitionByUnknownColumnError,
    TransformSqlContractError,
    TransformSqlDuplicateAliasError,
    TransformSqlFinalQueryShapeError,
    TransformSqlMultipleStatementsError,
    TransformSqlParseError,
    TransformSqlStarProjectionError,
    TransformSqlTopLevelSetOperationError,
    TransformSqlUntypedProjectionError,
    TransformTtlUnknownColumnError,
)
from streambuild.compiler.compile.models import Column
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.exceptions import (
    SqlAnalysisError,
    SqlDuplicateAliasError,
    SqlQueryShapeError,
    SqlStarProjectionError,
    SqlStatementCountError,
    SqlStorageReferenceError,
    SqlUntypedProjectionError,
)
from streambuild.compiler.sql_analysis.models import (
    SqlModelAnalysis,
    SqlOutputColumn,
    SqlStorageExpression,
)
from streambuild.compiler.sql_analysis.types import SqlStorageExpressionKind


def analyze_transform_model_sql(
    *,
    analyzer: SqlModelAnalyzer,
    transform_name: str,
    query: str,
    engine: str,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
) -> SqlModelAnalysis:
    """Analyze one model and translate boundary errors to compile-domain errors."""

    try:
        return analyzer.analyze(
            sql=query,
            engine=engine,
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
        )
    except SqlAnalysisError as error:
        raise _compile_error(transform_name=transform_name, query=query, error=error) from error


def derive_transform_output_columns(
    *, analyzer: SqlModelAnalyzer, transform_name: str, query: str
) -> tuple[Column, ...]:
    """Validate transform SQL and derive exact outer output columns."""

    analysis: SqlModelAnalysis = analyze_transform_model_sql(
        analyzer=analyzer,
        transform_name=transform_name,
        query=query,
        engine="MergeTree()",
        order_by=(),
        partition_by=None,
        ttl=None,
    )
    return tuple(_column(column) for column in analysis.output_columns)


def analyze_transform_sql(
    *, analyzer: SqlModelAnalyzer, transform_name: str, query: str
) -> tuple[tuple[Column, ...], bool]:
    """Return the retained legacy tuple from one mandatory model analysis."""

    analysis: SqlModelAnalysis = analyze_transform_model_sql(
        analyzer=analyzer,
        transform_name=transform_name,
        query=query,
        engine="MergeTree()",
        order_by=(),
        partition_by=None,
        ttl=None,
    )
    return (
        tuple(_column(column) for column in analysis.output_columns),
        analysis.aggregate_facts.has_semantics,
    )


def validate_order_by_expressions(
    *,
    analyzer: SqlModelAnalyzer,
    transform_name: str,
    order_by: Sequence[str],
    available_columns: Sequence[Column],
) -> None:
    """Validate ORDER BY expressions through mandatory SQL analysis."""

    _validate_storage(
        analyzer=analyzer,
        transform_name=transform_name,
        order_by=tuple(order_by),
        partition_by=None,
        ttl=None,
        available_columns=available_columns,
    )


def validate_partition_by_expression(
    *,
    analyzer: SqlModelAnalyzer,
    transform_name: str,
    partition_by: str | None,
    available_columns: Sequence[Column],
) -> None:
    """Validate PARTITION BY through mandatory SQL analysis."""

    _validate_storage(
        analyzer=analyzer,
        transform_name=transform_name,
        order_by=(),
        partition_by=partition_by,
        ttl=None,
        available_columns=available_columns,
    )


def validate_ttl_expression(
    *,
    analyzer: SqlModelAnalyzer,
    transform_name: str,
    ttl: str | None,
    available_columns: Sequence[Column],
) -> None:
    """Validate TTL through mandatory SQL analysis."""

    _validate_storage(
        analyzer=analyzer,
        transform_name=transform_name,
        order_by=(),
        partition_by=None,
        ttl=ttl,
        available_columns=available_columns,
    )


def _validate_storage(
    *,
    analyzer: SqlModelAnalyzer,
    transform_name: str,
    order_by: tuple[str, ...],
    partition_by: str | None,
    ttl: str | None,
    available_columns: Sequence[Column],
) -> None:
    try:
        _: tuple[SqlStorageExpression, ...] = analyzer.analyze_storage(
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
            output_columns=tuple(
                SqlOutputColumn(name=column.name, type=column.type) for column in available_columns
            ),
        )
    except SqlAnalysisError as error:
        raise _compile_error(transform_name=transform_name, query="", error=error) from error


def _compile_error(
    *, transform_name: str, query: str, error: SqlAnalysisError
) -> TransformSqlContractError:
    compile_error: TransformSqlContractError
    if isinstance(error, SqlStatementCountError):
        compile_error = TransformSqlMultipleStatementsError(transform_name, error.statement_count)
    elif isinstance(error, SqlQueryShapeError) and error.is_set_operation:
        compile_error = TransformSqlTopLevelSetOperationError(transform_name, error.statement_sql)
    elif isinstance(error, SqlQueryShapeError):
        compile_error = TransformSqlFinalQueryShapeError(transform_name, error.statement_type)
    elif isinstance(error, SqlStarProjectionError):
        compile_error = TransformSqlStarProjectionError(transform_name, error.column_index)
    elif isinstance(error, SqlUntypedProjectionError):
        compile_error = TransformSqlUntypedProjectionError(
            transform_name,
            error.column_index,
            error.projection_sql,
        )
    elif isinstance(error, SqlDuplicateAliasError):
        compile_error = TransformSqlDuplicateAliasError(transform_name, error.alias)
    elif isinstance(error, SqlStorageReferenceError):
        compile_error = _storage_error(transform_name=transform_name, error=error)
    else:
        compile_error = TransformSqlParseError(transform_name, query, str(error))
    compile_error.span = error.span
    return compile_error


def _storage_error(
    *, transform_name: str, error: SqlStorageReferenceError
) -> TransformSqlContractError:
    if error.kind == SqlStorageExpressionKind.ORDER_BY:
        return TransformOrderByUnknownColumnError(
            transform_name,
            error.expression,
            error.unknown_column_names,
            error.available_column_names,
        )
    if error.kind == SqlStorageExpressionKind.PARTITION_BY:
        return TransformPartitionByUnknownColumnError(
            transform_name,
            error.expression,
            error.unknown_column_names,
            error.available_column_names,
        )
    return TransformTtlUnknownColumnError(
        transform_name,
        error.expression,
        error.unknown_column_names,
        error.available_column_names,
    )


def _column(column: SqlOutputColumn) -> Column:
    return Column(name=column.name, type=column.type)
