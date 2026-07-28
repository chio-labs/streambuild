"""Render one SQL string literal through the mandatory analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import generate_sql_tree


def render_string_literal(*, value: str, dialect: str) -> str:
    """Return one dialect-safe SQL string literal."""

    tree: dict[str, Any] = {
        "literal": {
            "literal_type": "string",
            "value": value,
        }
    }
    return generate_sql_tree(tree=tree, dialect=dialect)
