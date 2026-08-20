"""Derive ClickHouse aggregate facts from a parsed model tree."""

from typing import Any

from streambuild.compiler.sql_analysis.constants import (
    CLICKHOUSE_AGGREGATE_COMBINATORS,
    CLICKHOUSE_AGGREGATE_FUNCTION_NAMES,
    CLICKHOUSE_AGGREGATE_STATE_FUNCTION_NAMES,
    CLICKHOUSE_AGGREGATING_ENGINE_NAMES,
    POLYGLOT_AGGREGATE_FUNCTION_KEY,
    POLYGLOT_ALIAS_VALUE_KEY,
    POLYGLOT_COMBINED_PARAMETERIZED_AGGREGATE_KEY,
    POLYGLOT_FUNCTION_KEY,
    POLYGLOT_GROUP_BY_KEY,
    POLYGLOT_IDENTIFIER_KEY,
    POLYGLOT_NAME_KEY,
)
from streambuild.compiler.sql_analysis.models import SqlAggregateFacts


def aggregate_facts(*, tree: dict[str, Any], engine: str) -> SqlAggregateFacts:
    """Return query and engine aggregation facts without generic aliases."""

    function_names: list[str]
    has_group_by: bool
    function_names, has_group_by = _scanned_aggregate_facts(node=tree, names=[], has_group_by=False)
    engine_name: str = engine.partition("(")[0].strip()
    normalized_engine_name: str = engine_name.lower().removeprefix("replicated")
    return SqlAggregateFacts(
        has_group_by=has_group_by,
        function_names=tuple(dict.fromkeys(function_names)),
        engine_name=engine_name,
        engine_has_aggregate_semantics=(
            normalized_engine_name in CLICKHOUSE_AGGREGATING_ENGINE_NAMES
        ),
    )


def _scanned_aggregate_facts(
    *, node: Any, names: list[str], has_group_by: bool
) -> tuple[list[str], bool]:
    if isinstance(node, list):
        item: Any
        for item in node:
            names, has_group_by = _scanned_aggregate_facts(
                node=item, names=names, has_group_by=has_group_by
            )
        return names, has_group_by
    if not isinstance(node, dict):
        return names, has_group_by
    has_group_by = has_group_by or node.get(POLYGLOT_GROUP_BY_KEY) is not None
    key: str
    payload: Any
    for key, payload in node.items():
        function_name: str | None = _function_name(key=key, payload=payload)
        if function_name is not None and _is_clickhouse_aggregate(function_name):
            names.append(function_name)
        if isinstance(payload, dict | list):
            names, has_group_by = _scanned_aggregate_facts(
                node=payload, names=names, has_group_by=has_group_by
            )
    return names, has_group_by


def _function_name(*, key: str, payload: Any) -> str | None:
    if key in {POLYGLOT_AGGREGATE_FUNCTION_KEY, POLYGLOT_FUNCTION_KEY} and isinstance(
        payload, dict
    ):
        name: Any = payload.get(POLYGLOT_NAME_KEY)
        return name if isinstance(name, str) else None
    if key == POLYGLOT_COMBINED_PARAMETERIZED_AGGREGATE_KEY and isinstance(payload, dict):
        identifier_wrapper: Any = payload.get(POLYGLOT_ALIAS_VALUE_KEY)
        if isinstance(identifier_wrapper, dict):
            identifier: Any = identifier_wrapper.get(POLYGLOT_IDENTIFIER_KEY)
            if isinstance(identifier, dict):
                name = identifier.get(POLYGLOT_NAME_KEY)
                return name if isinstance(name, str) else None
    return key if key.lower() in CLICKHOUSE_AGGREGATE_FUNCTION_NAMES else None


def _is_clickhouse_aggregate(function_name: str) -> bool:
    lowered_name: str = function_name.lower()
    if (
        lowered_name in CLICKHOUSE_AGGREGATE_FUNCTION_NAMES
        or lowered_name in CLICKHOUSE_AGGREGATE_STATE_FUNCTION_NAMES
    ):
        return True
    base_name: str = function_name
    changed: bool = True
    while changed:
        changed = False
        combinator: str
        for combinator in CLICKHOUSE_AGGREGATE_COMBINATORS:
            if base_name.lower().endswith(combinator.lower()):
                base_name = base_name[: -len(combinator)]
                changed = True
                break
    return base_name.lower() in CLICKHOUSE_AGGREGATE_FUNCTION_NAMES
