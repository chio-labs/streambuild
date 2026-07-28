"""Infer authored projection names from one compact Polyglot analysis."""

from __future__ import annotations

from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import analyze_query_facts
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_COMPACT_BRANCHES_KEY,
    POLYGLOT_COMPACT_IS_STAR_KEY,
    POLYGLOT_COMPACT_NAME_KEY,
    POLYGLOT_COMPACT_PROJECTIONS_KEY,
    POLYGLOT_COMPACT_SET_OPERATIONS_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError


def infer_projection_names_impl(*, sql: str, dialect: str) -> tuple[str, ...]:
    """Return the output column names of one query, rejecting unresolvable shapes."""

    facts: dict[str, Any] = analyze_query_facts(sql=sql, dialect=dialect)
    names: tuple[str, ...] = _projection_names(
        projections=_projection_list(payload=facts, key=POLYGLOT_COMPACT_PROJECTIONS_KEY)
    )
    _validate_branch_arity(facts=facts, projection_count=len(names))
    return names


def _projection_names(*, projections: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    if not projections:
        raise SqlAnalysisError("Query must project at least one column")
    names: list[str] = []
    projection: dict[str, Any]
    for projection in projections:
        if projection.get(POLYGLOT_COMPACT_IS_STAR_KEY) is True:
            raise SqlAnalysisError(
                "Query uses a SELECT * whose columns cannot be resolved from the "
                "authored CTEs; alias every projection explicitly"
            )
        name: Any = projection.get(POLYGLOT_COMPACT_NAME_KEY)
        if not isinstance(name, str) or not name:
            raise SqlAnalysisError("Query must alias every projected column")
        names.append(name)
    return tuple(names)


def _validate_branch_arity(*, facts: dict[str, Any], projection_count: int) -> None:
    set_operation: dict[str, Any]
    for set_operation in _projection_list(payload=facts, key=POLYGLOT_COMPACT_SET_OPERATIONS_KEY):
        branch: dict[str, Any]
        for branch in _projection_list(payload=set_operation, key=POLYGLOT_COMPACT_BRANCHES_KEY):
            branch_projections: tuple[dict[str, Any], ...] = _projection_list(
                payload=branch, key=POLYGLOT_COMPACT_PROJECTIONS_KEY
            )
            if len(branch_projections) != projection_count:
                raise SqlAnalysisError(
                    "Query must project the same column count in every set-operation branch"
                )


def _projection_list(*, payload: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    values: Any = payload.get(key)
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, dict))
