"""Invocation-scoped logical relation rewriting."""

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import build_validated_relation_rewrite
from streambuild.compiler.sql_analysis._helpers.scanning import (
    extract_references_impl,
    normalized_statement_sql,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import SqlReference


class SqlReferenceRewriter:
    """Rewrite references with one private Polyglot relation cache per invocation."""

    def __init__(self, *, dialect: str) -> None:
        self._dialect: str = dialect
        self._relation_cache: dict[str, tuple[dict[str, Any], str | None, dict[str, str]]] = {}

    def rewrite(self, *, sql: str, resolver: dict[str, str]) -> str:
        """Replace logical relation calls while preserving authored surrounding text."""

        references: tuple[SqlReference, ...] = extract_references_impl(sql)
        reference: SqlReference
        for reference in references:
            if reference.name not in resolver:
                raise SqlAnalysisError(f"Unresolved ref: {reference.name}", span=reference.span)
        canonical_relation_by_target: dict[str, str]
        canonical_relation_by_target, self._relation_cache = build_validated_relation_rewrite(
            sql=sql,
            dialect=self._dialect,
            references=references,
            resolver=resolver,
            relation_cache=self._relation_cache,
        )
        rewritten_sql: str = sql
        for reference in reversed(references):
            target: str = resolver[reference.name]
            rewritten_sql = (
                rewritten_sql[: reference.span.start]
                + canonical_relation_by_target[target]
                + rewritten_sql[reference.span.end :]
            )
        return normalized_statement_sql(rewritten_sql)
