"""Invocation-scoped model SQL analysis and canonical generation."""

from collections.abc import Mapping
from typing import Any

from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER
from streambuild.compiler.sql_analysis._helpers.model_analysis import analyze_model_sql_impl
from streambuild.compiler.sql_analysis._helpers.polyglot import (
    build_resolved_query,
    canonical_query_with_database_template,
)
from streambuild.compiler.sql_analysis._helpers.storage import analyze_storage_expressions
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import (
    SqlModelAnalysis,
    SqlOutputColumn,
    SqlResolvedQuery,
    SqlStorageExpression,
)
from streambuild.compiler.sql_analysis.types import ProjectionTypeCache


class SqlModelAnalyzer:
    """Own private parsed model state for one complete compiler invocation."""

    def __init__(self, *, dialect: str) -> None:
        self._dialect: str = dialect
        self._resolution_by_analysis: dict[
            SqlModelAnalysis, tuple[dict[str, Any], tuple[tuple[Any, Any], ...], str | None]
        ] = {}
        self._relation_cache: dict[str, tuple[dict[str, Any], str | None, dict[str, str]]] = {}
        self._type_cache: ProjectionTypeCache = {}

    def analyze(
        self,
        *,
        sql: str,
        engine: str,
        order_by: tuple[str, ...],
        partition_by: str | None,
        ttl: str | None,
    ) -> SqlModelAnalysis:
        """Analyze one authored model and retain only private rewrite state."""

        analysis: SqlModelAnalysis
        tree: dict[str, Any]
        reference_slots: tuple[tuple[Any, Any], ...]
        raw_relation: str | None
        analysis, tree, self._type_cache, reference_slots, raw_relation = analyze_model_sql_impl(
            sql=sql,
            engine=engine,
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
            dialect=self._dialect,
            type_cache=self._type_cache,
        )
        self._resolution_by_analysis[analysis] = (tree, reference_slots, raw_relation)
        return analysis

    def resolve(
        self,
        *,
        analysis: SqlModelAnalysis,
        resolver: Mapping[str, str],
    ) -> SqlResolvedQuery:
        """Resolve and qualify a previously analyzed model without reparsing it."""

        resolution: tuple[dict[str, Any], tuple[tuple[Any, Any], ...], str | None] | None = (
            self._resolution_by_analysis.get(analysis)
        )
        if resolution is None:
            raise SqlAnalysisError("Model analysis does not belong to this compiler invocation")
        resolved_query: SqlResolvedQuery
        resolved_query, self._relation_cache = build_resolved_query(
            tree=resolution[0],
            reference_slots=resolution[1],
            raw_relation=resolution[2],
            authored_sql=analysis.authored_sql,
            dialect=self._dialect,
            references=analysis.references,
            resolver=resolver,
            relation_cache=self._relation_cache,
            database_placeholder=ADAPTER_DATABASE_PLACEHOLDER,
        )
        return resolved_query

    def canonicalize_query(self, *, sql: str) -> SqlResolvedQuery:
        """Generate canonical and adapter-template forms of a generated query."""

        return canonical_query_with_database_template(
            sql=sql,
            dialect=self._dialect,
            database_placeholder=ADAPTER_DATABASE_PLACEHOLDER,
        )

    def analyze_storage(
        self,
        *,
        order_by: tuple[str, ...],
        partition_by: str | None,
        ttl: str | None,
        output_columns: tuple[SqlOutputColumn, ...],
    ) -> tuple[SqlStorageExpression, ...]:
        """Analyze standalone storage clauses through this invocation's dialect."""

        return analyze_storage_expressions(
            order_by=order_by,
            partition_by=partition_by,
            ttl=ttl,
            output_columns=output_columns,
            dialect=self._dialect,
        )
