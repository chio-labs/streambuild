"""Rewrite one SELECT through the mandatory SQL-analysis boundary."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.aggregates import build_aggregate_facts
from streambuild.compiler.sql_analysis._helpers.polyglot import (
    collect_tree_facts,
    generate_sql_tree,
    parse_sql_tree,
)
from streambuild.compiler.sql_analysis._helpers.query_rewriting import (
    append_query_predicate,
    get_select_payload,
    prepend_query_ctes,
    rewrite_query_tree,
)
from streambuild.compiler.sql_analysis.models import (
    SqlAggregateFacts,
    SqlNamedQuery,
    SqlQueryRewriteResult,
    SqlRelationRewrite,
)


def rewrite_query(
    *,
    sql: str,
    dialect: str,
    relation_rewrites: tuple[SqlRelationRewrite, ...] = (),
    predicate: str | None = None,
    prepend_ctes: tuple[SqlNamedQuery, ...] = (),
) -> SqlQueryRewriteResult:
    """Rewrite relations, predicate, and CTEs in one parsed SELECT."""

    tree: dict[str, Any] = parse_sql_tree(sql=sql, dialect=dialect)
    _ = get_select_payload(tree)
    rewrite_query_tree(tree=tree, rewrites=relation_rewrites, dialect=dialect)
    if predicate is not None:
        append_query_predicate(tree=tree, predicate=predicate, dialect=dialect)
    prepend_query_ctes(tree=tree, named_queries=prepend_ctes, dialect=dialect)
    function_names, has_group_by, _, _ = collect_tree_facts(tree=tree)
    facts: SqlAggregateFacts = build_aggregate_facts(
        function_names=function_names, has_group_by=has_group_by, engine=""
    )
    return SqlQueryRewriteResult(
        query=generate_sql_tree(tree=tree, dialect=dialect),
        has_aggregate_semantics=facts.has_semantics,
    )
