"""Analyze one query or ClickHouse catalog statement."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import parse_sql_tree
from streambuild.compiler.sql_analysis._helpers.query_rewriting import analyze_catalog_tree
from streambuild.compiler.sql_analysis.models import SqlCatalogAnalysis


def analyze_catalog_sql(*, sql: str, dialect: str) -> SqlCatalogAnalysis:
    """Return canonical catalog and relation facts through Polyglot."""

    tree: dict[str, Any] = parse_sql_tree(sql=sql, dialect=dialect)
    return analyze_catalog_tree(tree=tree, dialect=dialect)
