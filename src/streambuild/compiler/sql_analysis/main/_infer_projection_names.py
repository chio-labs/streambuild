"""Public entrypoint for authored projection-name inference."""

from __future__ import annotations

from streambuild.compiler.sql_analysis._helpers.projection_names import (
    infer_projection_names_impl,
)


def infer_projection_names(*, sql: str, dialect: str) -> tuple[str, ...]:
    """Return the output column names produced by one authored query."""

    return infer_projection_names_impl(sql=sql, dialect=dialect)
