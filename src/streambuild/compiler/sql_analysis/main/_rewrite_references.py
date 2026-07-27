"""Rewrite logical relation references through mandatory Polyglot validation."""

from collections.abc import Mapping

from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)


def rewrite_references(*, sql: str, resolver: Mapping[str, str], dialect: str) -> str:
    """Replace logical relation calls while preserving authored non-reference text."""

    rewriter: SqlReferenceRewriter = SqlReferenceRewriter(dialect=dialect)
    return rewriter.rewrite(sql=sql, resolver=dict(resolver))
