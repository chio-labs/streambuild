"""Rewrite one placeholder-qualified template while preserving author bytes."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.aggregates import build_aggregate_facts
from streambuild.compiler.sql_analysis._helpers.polyglot import (
    collect_tree_facts,
    parse_sql_tree,
)
from streambuild.compiler.sql_analysis._helpers.query_rewriting import get_select_payload
from streambuild.compiler.sql_analysis._helpers.scanning import (
    append_template_predicate_impl,
    merge_template_ctes_impl,
    rewrite_template_relations_impl,
)
from streambuild.compiler.sql_analysis.models import (
    SqlAggregateFacts,
    SqlNamedQuery,
    SqlQueryRewriteResult,
    SqlRelationRewrite,
)


def rewrite_template_query(
    *,
    template: str,
    dialect: str,
    database_placeholder: str,
    relation_rewrites: tuple[SqlRelationRewrite, ...] = (),
    predicate: str | None = None,
    prepend_ctes: tuple[SqlNamedQuery, ...] = (),
) -> SqlQueryRewriteResult:
    """Rewrite relations, predicate, and CTEs through byte-preserving text edits."""

    rewritten: str = rewrite_template_relations_impl(
        template=template,
        relation_rewrites=relation_rewrites,
        database_placeholder=database_placeholder,
    )
    if predicate is not None:
        rewritten = append_template_predicate_impl(template=rewritten, predicate=predicate)
    rewritten = merge_template_ctes_impl(template=rewritten, named_queries=prepend_ctes)
    tree: dict[str, Any] = parse_sql_tree(sql=rewritten, dialect=dialect)
    _ = get_select_payload(tree)
    function_names, has_group_by, _, _ = collect_tree_facts(tree=tree)
    facts: SqlAggregateFacts = build_aggregate_facts(
        function_names=function_names, has_group_by=has_group_by, engine=""
    )
    return SqlQueryRewriteResult(
        query=rewritten,
        has_aggregate_semantics=facts.has_semantics,
    )
