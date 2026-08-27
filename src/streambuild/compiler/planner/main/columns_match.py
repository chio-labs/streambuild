"""Semantic ClickHouse column comparison entrypoint."""

from streambuild.compiler.compile.models import Column
from streambuild.compiler.planner.exceptions import DeploymentPlanError
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main._normalize_data_type import normalize_sql_data_type


def columns_match(
    *, desired_columns: tuple[Column, ...], actual_columns: tuple[Column, ...]
) -> bool:
    """Return whether ordered columns have equivalent names, types, and defaults."""

    if len(desired_columns) != len(actual_columns):
        return False
    return all(
        _column_matches(desired_column=desired, actual_column=actual)
        for desired, actual in zip(desired_columns, actual_columns, strict=True)
    )


def _column_matches(*, desired_column: Column, actual_column: Column) -> bool:
    """Return whether one desired and actual column are semantically equivalent."""

    return (
        desired_column.name == actual_column.name
        and _normalize_type(desired_column.type) == _normalize_type(actual_column.type)
        and desired_column.default == actual_column.default
    )


def _normalize_type(type_sql: str) -> str:
    try:
        return normalize_sql_data_type(sql=type_sql, dialect="clickhouse")
    except SqlAnalysisError as error:
        raise DeploymentPlanError(
            f"Could not normalize ClickHouse type '{type_sql}': {error}"
        ) from None
