"""Parse one SQL expression list through the mandatory analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import parse_sql_tree
from streambuild.compiler.sql_analysis._helpers.query_rewriting import expression_list


def parse_expression_list(*, sql: str, dialect: str) -> tuple[str, ...]:
    """Return canonical top-level expressions without textual comma splitting."""

    tree: dict[str, Any] = parse_sql_tree(sql=f"SELECT {sql}", dialect=dialect)
    return expression_list(tree=tree, dialect=dialect)
