"""Build one INSERT SELECT through the mandatory SQL-analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import generate_sql_tree, parse_sql_tree
from streambuild.compiler.sql_analysis.constants import POLYGLOT_INSERT_KEY, POLYGLOT_QUERY_KEY
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError


def build_insert_query(*, target_relation: str, query: str, dialect: str) -> str:
    """Parse and generate one INSERT SELECT statement."""

    tree: dict[str, Any] = parse_sql_tree(
        sql=f"INSERT INTO {target_relation} {query}", dialect=dialect
    )
    insert_payload: Any = tree.get(POLYGLOT_INSERT_KEY)
    if not isinstance(insert_payload, dict) or not isinstance(
        insert_payload.get(POLYGLOT_QUERY_KEY), dict
    ):
        raise SqlAnalysisError("Replay output expects an INSERT SELECT query")
    return generate_sql_tree(tree=tree, dialect=dialect)
