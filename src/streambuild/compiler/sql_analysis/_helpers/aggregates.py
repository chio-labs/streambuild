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

_FUNCTION_NAME_KEYS: frozenset[str] = frozenset(
    {
        POLYGLOT_AGGREGATE_FUNCTION_KEY,
        POLYGLOT_FUNCTION_KEY,
        POLYGLOT_COMBINED_PARAMETERIZED_AGGREGATE_KEY,
    }
)
_NESTED_PAYLOAD_TYPES: frozenset[type] = frozenset({dict, list})


def aggregate_facts(*, tree: dict[str, Any], engine: str) -> SqlAggregateFacts:
    """Return query and engine aggregation facts without generic aliases."""

    function_names: list[str]
    has_group_by: bool
    function_names, _, has_group_by = _scanned_aggregate_facts(node=tree, names=[], keyed_names={})
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
    *, node: Any, names: list[str], keyed_names: dict[str, str]
) -> tuple[list[str], dict[str, str], bool]:
    has_group_by: bool = False
    nested_group_by: bool
    if type(node) is list:
        item: Any
        for item in node:
            if type(item) in _NESTED_PAYLOAD_TYPES:
                names, keyed_names, nested_group_by = _scanned_aggregate_facts(
                    node=item, names=names, keyed_names=keyed_names
                )
                if nested_group_by:
                    has_group_by = True
        return names, keyed_names, has_group_by
    if type(node) is not dict:
        return names, keyed_names, False
    if node.get(POLYGLOT_GROUP_BY_KEY) is not None:
        has_group_by = True
    key: str
    payload: Any
    for key, payload in node.items():
        if key in _FUNCTION_NAME_KEYS:
            payload_name: str | None = _function_name(key=key, payload=payload)
            if payload_name is not None and _is_clickhouse_aggregate(payload_name):
                names.append(payload_name)
        else:
            keyed_name: str | None = keyed_names.get(key)
            if keyed_name is None:
                keyed_name = _keyed_function_name(key)
                keyed_names[key] = keyed_name
            if keyed_name:
                names.append(keyed_name)
        if type(payload) in _NESTED_PAYLOAD_TYPES:
            names, keyed_names, nested_group_by = _scanned_aggregate_facts(
                node=payload, names=names, keyed_names=keyed_names
            )
            if nested_group_by:
                has_group_by = True
    return names, keyed_names, has_group_by


def _keyed_function_name(key: str) -> str:
    if key in CLICKHOUSE_AGGREGATE_FUNCTION_NAMES:
        return key
    if not key.islower() and key.lower() in CLICKHOUSE_AGGREGATE_FUNCTION_NAMES:
        return key
    return ""


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
