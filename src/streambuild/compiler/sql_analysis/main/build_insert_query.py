"""Build one INSERT SELECT through the mandatory SQL-analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import parse_sql_tree
from streambuild.compiler.sql_analysis.constants import POLYGLOT_INSERT_KEY, POLYGLOT_QUERY_KEY
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError


def build_insert_query(*, target_relation: str, query: str, dialect: str) -> str:
    """Compose one byte-preserving INSERT SELECT statement validated by parsing."""

    statement: str = f"INSERT INTO {target_relation}\n{query}"
    tree: dict[str, Any] = parse_sql_tree(sql=statement, dialect=dialect)
    insert_payload: Any = tree.get(POLYGLOT_INSERT_KEY)
    if not isinstance(insert_payload, dict) or not isinstance(
        insert_payload.get(POLYGLOT_QUERY_KEY), dict
    ):
        raise SqlAnalysisError("Replay output expects an INSERT SELECT query")
    return statement
