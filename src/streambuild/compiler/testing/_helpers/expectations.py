"""Expected-column inference and target-type casting for SQL tests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main._infer_projection_names import infer_projection_names
from streambuild.compiler.testing.exceptions import SqlTestAssemblyError


def derive_column_names(
    *,
    query: str,
    file_path: Path,
    label: str,
    authored_ctes: tuple[tuple[str, str], ...],
    dialect: str,
) -> tuple[str, ...]:
    """Infer the output column names of one authored test query through Polyglot."""

    try:
        return infer_projection_names(
            sql=wrap_with_ctes(query=query, ctes=authored_ctes),
            dialect=dialect,
        )
    except SqlAnalysisError as error:
        raise SqlTestAssemblyError(
            f"SQL test '{file_path}' cannot resolve {label} columns: {error}"
        ) from error


def wrap_with_ctes(*, query: str, ctes: tuple[tuple[str, str], ...]) -> str:
    """Prefix one query with the authored CTEs it may reference."""

    if not ctes:
        return query
    rendered: str = ",\n".join(f"{name} AS (\n{cte_query}\n)" for name, cte_query in ctes)
    return f"WITH\n{rendered}\n{query}"


def build_typed_expected_query(
    *,
    expected_query: str,
    expected_column_names: tuple[str, ...],
    output_column_type_by_name: Mapping[str, str],
) -> str:
    """Cast every expected column to its compiled target type."""

    cast_projections: str = ",\n".join(
        f"    CAST({column_name} AS {output_column_type_by_name[column_name]}) AS {column_name}"
        for column_name in expected_column_names
    )
    return f"SELECT\n{cast_projections}\nFROM (\n{expected_query}\n) AS expected_source"
