"""Rewrite one executed query while preserving placeholder-template bytes."""

from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER
from streambuild.compiler.sql_analysis.main.rewrite_query import rewrite_query
from streambuild.compiler.sql_analysis.main.rewrite_template_query import rewrite_template_query
from streambuild.compiler.sql_analysis.models import (
    SqlNamedQuery,
    SqlQueryRewriteResult,
    SqlRelationRewrite,
)


def rewrite_executed_query(
    *,
    sql: str,
    dialect: str,
    relation_rewrites: tuple[SqlRelationRewrite, ...] = (),
    predicate: str | None = None,
    prepend_ctes: tuple[SqlNamedQuery, ...] = (),
) -> SqlQueryRewriteResult:
    """Rewrite placeholder-qualified templates textually or canonical SQL via the AST."""

    if ADAPTER_DATABASE_PLACEHOLDER in sql:
        return rewrite_template_query(
            template=sql,
            dialect=dialect,
            database_placeholder=ADAPTER_DATABASE_PLACEHOLDER,
            relation_rewrites=relation_rewrites,
            predicate=predicate,
            prepend_ctes=prepend_ctes,
        )
    return rewrite_query(
        sql=sql,
        dialect=dialect,
        relation_rewrites=relation_rewrites,
        predicate=predicate,
        prepend_ctes=prepend_ctes,
    )
