"""Validate one SQL query through the mandatory analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import parse_sql_tree
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_EXCEPT_KEY,
    POLYGLOT_INTERSECT_KEY,
    POLYGLOT_SELECT_KEY,
    POLYGLOT_UNION_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError


def validate_query(*, sql: str, dialect: str) -> None:
    """Require exactly one SELECT or set-operation query."""

    tree: dict[str, Any] = parse_sql_tree(sql=sql, dialect=dialect)
    if not {
        POLYGLOT_SELECT_KEY,
        POLYGLOT_UNION_KEY,
        POLYGLOT_INTERSECT_KEY,
        POLYGLOT_EXCEPT_KEY,
    }.intersection(tree):
        raise SqlAnalysisError("SQL statement must be a SELECT or set-operation query")
