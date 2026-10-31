"""Invocation-scoped logical relation rewriting."""

import sqltide._native as _native
from sqltide.compiler.sql_analysis._helpers.polyglot import native_references, sql_tree_error
from sqltide.compiler.sql_analysis._helpers.scanning import (
    extract_references_impl,
    normalized_statement_sql,
)
from sqltide.compiler.sql_analysis.exceptions import SqlAnalysisError
from sqltide.compiler.sql_analysis.models import SqlReference


class SqlReferenceRewriter:
    """Rewrite references with one private Polyglot relation cache per invocation."""

    def __init__(self, *, dialect: str) -> None:
        self._analyzer: _native.SqlTreeAnalyzer = _native.SqlTreeAnalyzer(dialect)

    def rewrite(self, *, sql: str, resolver: dict[str, str]) -> str:
        """Replace logical relation calls while preserving authored surrounding text."""

        references: tuple[SqlReference, ...] = extract_references_impl(sql)
        reference: SqlReference
        for reference in references:
            if reference.name not in resolver:
                raise SqlAnalysisError(f"Unresolved ref: {reference.name}", span=reference.span)
        try:
            canonical_relation_by_target: dict[str, str] = self._analyzer.rewrite_relations(
                sql, native_references(references), resolver
            )
        except _native.SqlTreeError as error:
            raise sql_tree_error(error) from None
        rewritten_sql: str = sql
        for reference in reversed(references):
            target: str = resolver[reference.name]
            rewritten_sql = (
                rewritten_sql[: reference.span.start]
                + canonical_relation_by_target[target]
                + rewritten_sql[reference.span.end :]
            )
        return normalized_statement_sql(rewritten_sql)
