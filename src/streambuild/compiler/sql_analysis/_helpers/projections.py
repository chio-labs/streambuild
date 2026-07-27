"""Build strict model projections from private Polyglot payloads."""

from typing import Any, cast

from streambuild.compiler.sql_analysis._helpers.polyglot import generate_sql_tree
from streambuild.compiler.sql_analysis._helpers.projection_spans import (
    outer_double_colon_type,
    outer_star_span,
)
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_ALIAS_KEY,
    POLYGLOT_ALIAS_VALUE_KEY,
    POLYGLOT_CAST_KEY,
    POLYGLOT_COMPACT_COLUMN_KEY,
    POLYGLOT_COMPACT_CONFIDENCE_KEY,
    POLYGLOT_COMPACT_INDEX_KEY,
    POLYGLOT_COMPACT_PROJECTIONS_KEY,
    POLYGLOT_COMPACT_SOURCE_NAME_KEY,
    POLYGLOT_COMPACT_UPSTREAM_KEY,
    POLYGLOT_DATA_TYPE_KEY,
    POLYGLOT_DOUBLE_COLON_SYNTAX_KEY,
    POLYGLOT_EXPRESSIONS_KEY,
    POLYGLOT_NAME_KEY,
    POLYGLOT_STAR_KEY,
    POLYGLOT_TO_KEY,
    POLYGLOT_TRY_CAST_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import (
    SqlAnalysisError,
    SqlDuplicateAliasError,
    SqlStarProjectionError,
    SqlUntypedProjectionError,
)
from streambuild.compiler.sql_analysis.models import (
    SqlLineageSourceFact,
    SqlOutputColumn,
    SqlProjection,
    SqlSourceSpan,
)
from streambuild.compiler.sql_analysis.types import SqlLineageConfidence

_POLYGLOT_CUSTOM_DATA_TYPE: str = "custom"


def build_model_projections(
    *,
    select_payload: dict[str, Any],
    sql: str,
    spans: tuple[SqlSourceSpan, ...],
    compact_analysis: dict[str, Any],
    dialect: str,
) -> tuple[SqlProjection, ...]:
    """Validate and return strict typed outer projections."""

    expressions: Any = select_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list) or len(expressions) != len(spans):
        raise SqlAnalysisError("Polyglot projection count did not match authored SQL")
    compact_by_index: dict[int, dict[str, Any]] = _compact_projections(compact_analysis)
    projections: list[SqlProjection] = []
    seen_aliases: set[str] = set()
    expression: Any
    for index, expression in enumerate(expressions, start=1):
        span: SqlSourceSpan = spans[index - 1]
        if not isinstance(expression, dict):
            raise SqlUntypedProjectionError(
                column_index=index,
                projection_sql="",
                span=span,
            )
        expression_tree: dict[str, Any] = cast(dict[str, Any], expression)
        if _is_outer_star(expression_tree):
            raise SqlStarProjectionError(
                column_index=index,
                span=outer_star_span(sql=sql, projection_span=span),
            )
        alias_payload: Any = expression_tree.get(POLYGLOT_ALIAS_KEY)
        cast_payload: dict[str, Any] | None = _cast_payload(alias_payload)
        alias: str | None = _projection_alias(alias_payload)
        if cast_payload is None or alias is None:
            projection_sql: str = generate_sql_tree(tree=expression_tree, dialect=dialect)
            raise SqlUntypedProjectionError(
                column_index=index,
                projection_sql=projection_sql,
                span=span,
            )
        authored_double_colon_type: str | None = outer_double_colon_type(
            sql=sql,
            projection_span=span,
        )
        if (
            cast_payload.get(POLYGLOT_DOUBLE_COLON_SYNTAX_KEY) is True
            and authored_double_colon_type is not None
        ):
            cast_payload[POLYGLOT_TO_KEY] = {
                POLYGLOT_DATA_TYPE_KEY: _POLYGLOT_CUSTOM_DATA_TYPE,
                POLYGLOT_NAME_KEY: authored_double_colon_type,
            }
        projection_sql = generate_sql_tree(tree=expression_tree, dialect=dialect)
        if alias in seen_aliases:
            raise SqlDuplicateAliasError(alias=alias, span=span)
        seen_aliases.add(alias)
        type_payload: Any = cast_payload.get(POLYGLOT_TO_KEY)
        if not isinstance(type_payload, dict):
            raise SqlUntypedProjectionError(
                column_index=index,
                projection_sql=projection_sql,
                span=span,
            )
        projections.append(
            SqlProjection(
                index=index,
                sql=projection_sql,
                output=SqlOutputColumn(
                    name=alias,
                    type=generate_sql_tree(
                        tree={POLYGLOT_DATA_TYPE_KEY: type_payload},
                        dialect=dialect,
                    ),
                ),
                span=span,
                upstream=_upstream_facts(compact_by_index.get(index - 1)),
            )
        )
    return tuple(projections)


def _compact_projections(compact_analysis: dict[str, Any]) -> dict[int, dict[str, Any]]:
    projections: Any = compact_analysis.get(POLYGLOT_COMPACT_PROJECTIONS_KEY)
    if not isinstance(projections, list):
        return {}
    indexed: dict[int, dict[str, Any]] = {}
    projection: Any
    for projection in projections:
        if isinstance(projection, dict):
            index: Any = projection.get(POLYGLOT_COMPACT_INDEX_KEY)
            if isinstance(index, int):
                indexed[index] = projection
    return indexed


def _upstream_facts(projection: dict[str, Any] | None) -> tuple[SqlLineageSourceFact, ...]:
    if projection is None:
        return ()
    upstream: Any = projection.get(POLYGLOT_COMPACT_UPSTREAM_KEY)
    if not isinstance(upstream, list):
        return ()
    facts: set[SqlLineageSourceFact] = set()
    item: Any
    for item in upstream:
        if isinstance(item, dict):
            relation_name: Any = item.get(POLYGLOT_COMPACT_SOURCE_NAME_KEY)
            column_name: Any = item.get(POLYGLOT_COMPACT_COLUMN_KEY)
            confidence: Any = item.get(POLYGLOT_COMPACT_CONFIDENCE_KEY)
            if isinstance(relation_name, str) and isinstance(column_name, str):
                facts.add(
                    SqlLineageSourceFact(
                        relation_name=relation_name,
                        column_name=column_name,
                        confidence=(
                            SqlLineageConfidence.RESOLVED
                            if confidence == SqlLineageConfidence.RESOLVED
                            else SqlLineageConfidence.UNKNOWN
                        ),
                    )
                )
    return tuple(sorted(facts, key=lambda fact: (fact.relation_name, fact.column_name)))


def _is_outer_star(expression: dict[str, Any]) -> bool:
    if POLYGLOT_STAR_KEY in expression:
        return True
    alias_payload: Any = expression.get(POLYGLOT_ALIAS_KEY)
    if not isinstance(alias_payload, dict):
        return False
    aliased_expression: Any = alias_payload.get(POLYGLOT_ALIAS_VALUE_KEY)
    return isinstance(aliased_expression, dict) and POLYGLOT_STAR_KEY in aliased_expression


def _cast_payload(alias_payload: Any) -> dict[str, Any] | None:
    if not isinstance(alias_payload, dict):
        return None
    expression: Any = alias_payload.get(POLYGLOT_ALIAS_VALUE_KEY)
    if not isinstance(expression, dict):
        return None
    cast_payload: Any = expression.get(POLYGLOT_CAST_KEY) or expression.get(POLYGLOT_TRY_CAST_KEY)
    return cast_payload if isinstance(cast_payload, dict) else None


def _projection_alias(alias_payload: Any) -> str | None:
    if not isinstance(alias_payload, dict):
        return None
    identifier: Any = alias_payload.get(POLYGLOT_ALIAS_KEY)
    if not isinstance(identifier, dict):
        return None
    name: Any = identifier.get(POLYGLOT_NAME_KEY)
    return name if isinstance(name, str) and name else None
