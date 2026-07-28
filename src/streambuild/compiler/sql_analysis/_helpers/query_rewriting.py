"""Apache-2.0: SQLBuild planner/_helpers/scenario/relations.py@7e3b2f854f05."""

from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import (
    _parse_relation,
    parse_sql_tree,
)
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_ALIAS_KEY,
    POLYGLOT_ALIAS_VALUE_KEY,
    POLYGLOT_AND_KEY,
    POLYGLOT_CTES_KEY,
    POLYGLOT_EXPRESSIONS_KEY,
    POLYGLOT_FROM_KEY,
    POLYGLOT_JOINS_KEY,
    POLYGLOT_LEFT_KEY,
    POLYGLOT_NAME_KEY,
    POLYGLOT_PAREN_KEY,
    POLYGLOT_RIGHT_KEY,
    POLYGLOT_SCHEMA_KEY,
    POLYGLOT_SELECT_KEY,
    POLYGLOT_TABLE_KEY,
    POLYGLOT_WHERE_CLAUSE_KEY,
    POLYGLOT_WITH_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import SqlNamedQuery, SqlRelationRewrite

_RELATION_ALIAS_FIELDS: tuple[str, ...] = (
    POLYGLOT_ALIAS_KEY,
    "alias_explicit_as",
    "alias_keyword",
    "column_aliases",
    "trailing_comments",
)


def get_select_payload(tree: dict[str, Any]) -> dict[str, Any]:
    """Return the outer SELECT payload or reject another statement shape."""

    payload: Any = tree.get(POLYGLOT_SELECT_KEY)
    if not isinstance(payload, dict):
        raise SqlAnalysisError("Query rewrite expects a SELECT query")
    return payload


def rewrite_query_tree(
    *, tree: dict[str, Any], rewrites: tuple[SqlRelationRewrite, ...], dialect: str
) -> None:
    """Rewrite eligible relations throughout one SELECT tree."""

    select_payload: dict[str, Any] = get_select_payload(tree)
    _rewrite_select(
        select_payload=select_payload,
        rewrites=rewrites,
        visible_ctes=frozenset(),
        dialect=dialect,
    )


def append_query_predicate(*, tree: dict[str, Any], predicate: str, dialect: str) -> None:
    """Conjoin one parsed predicate with the outer SELECT predicate."""

    select_payload: dict[str, Any] = get_select_payload(tree)
    predicate_tree: dict[str, Any] = parse_sql_tree(
        sql=f"SELECT 1 WHERE {predicate}", dialect=dialect
    )
    predicate_payload: Any = get_select_payload(predicate_tree).get(POLYGLOT_WHERE_CLAUSE_KEY)
    if not isinstance(predicate_payload, dict):
        raise SqlAnalysisError("Replay boundary is not a valid SQL predicate")
    replay_predicate: Any = predicate_payload.get(POLYGLOT_ALIAS_VALUE_KEY)
    if not isinstance(replay_predicate, dict):
        raise SqlAnalysisError("Replay boundary is not a valid SQL predicate")
    existing_where: Any = select_payload.get(POLYGLOT_WHERE_CLAUSE_KEY)
    if not isinstance(existing_where, dict):
        select_payload[POLYGLOT_WHERE_CLAUSE_KEY] = {POLYGLOT_ALIAS_VALUE_KEY: replay_predicate}
        return
    existing_predicate: Any = existing_where.get(POLYGLOT_ALIAS_VALUE_KEY)
    if not isinstance(existing_predicate, dict):
        raise SqlAnalysisError("Existing WHERE clause is not a valid SQL predicate")
    existing_where[POLYGLOT_ALIAS_VALUE_KEY] = _parenthesized_and(
        left=existing_predicate,
        right=replay_predicate,
    )


def prepend_query_ctes(
    *, tree: dict[str, Any], named_queries: tuple[SqlNamedQuery, ...], dialect: str
) -> None:
    """Prepend parsed CTEs while preserving authored CTE ordering."""

    if not named_queries:
        return
    select_payload: dict[str, Any] = get_select_payload(tree)
    existing_with: Any = select_payload.get(POLYGLOT_WITH_KEY)
    existing_ctes: list[Any] = (
        existing_with.get(POLYGLOT_CTES_KEY, []) if isinstance(existing_with, dict) else []
    )
    existing_names: frozenset[str] = _cte_names(existing_ctes)
    requested_names: tuple[str, ...] = tuple(named_query.name for named_query in named_queries)
    if existing_names.intersection(requested_names) or len(set(requested_names)) != len(
        requested_names
    ):
        raise SqlAnalysisError("Replay CTE name collides with an authored CTE")
    new_ctes: list[dict[str, Any]] = [
        _parse_cte(named_query=named_query, dialect=dialect) for named_query in named_queries
    ]
    if isinstance(existing_with, dict):
        existing_with[POLYGLOT_CTES_KEY] = [*new_ctes, *existing_ctes]
        return
    template_tree: dict[str, Any] = parse_sql_tree(
        sql=f"WITH {named_queries[0].name} AS ({named_queries[0].query}) SELECT 1",
        dialect=dialect,
    )
    template_with: Any = get_select_payload(template_tree).get(POLYGLOT_WITH_KEY)
    if not isinstance(template_with, dict):
        raise SqlAnalysisError("Replay CTE could not be parsed")
    template_with[POLYGLOT_CTES_KEY] = new_ctes
    select_payload[POLYGLOT_WITH_KEY] = template_with


def _rewrite_select(
    *,
    select_payload: dict[str, Any],
    rewrites: tuple[SqlRelationRewrite, ...],
    visible_ctes: frozenset[str],
    dialect: str,
) -> None:
    local_ctes: list[Any] = _select_ctes(select_payload)
    all_visible_ctes: frozenset[str] = visible_ctes | _cte_names(local_ctes)
    cte: Any
    for cte in local_ctes:
        if isinstance(cte, dict):
            _rewrite_node(
                node=cte.get(POLYGLOT_ALIAS_VALUE_KEY),
                rewrites=rewrites,
                visible_ctes=all_visible_ctes,
                dialect=dialect,
            )
    _rewrite_relation_slots(
        select_payload=select_payload,
        rewrites=rewrites,
        visible_ctes=all_visible_ctes,
        dialect=dialect,
    )
    key: str
    value: Any
    for key, value in select_payload.items():
        if key not in {POLYGLOT_FROM_KEY, POLYGLOT_JOINS_KEY, POLYGLOT_WITH_KEY}:
            _rewrite_node(
                node=value,
                rewrites=rewrites,
                visible_ctes=all_visible_ctes,
                dialect=dialect,
            )


def _rewrite_node(
    *,
    node: Any,
    rewrites: tuple[SqlRelationRewrite, ...],
    visible_ctes: frozenset[str],
    dialect: str,
) -> None:
    if isinstance(node, list):
        item: Any
        for item in node:
            _rewrite_node(
                node=item,
                rewrites=rewrites,
                visible_ctes=visible_ctes,
                dialect=dialect,
            )
        return
    if not isinstance(node, dict):
        return
    select_payload: Any = node.get(POLYGLOT_SELECT_KEY)
    if isinstance(select_payload, dict):
        _rewrite_select(
            select_payload=select_payload,
            rewrites=rewrites,
            visible_ctes=visible_ctes,
            dialect=dialect,
        )
        return
    value: Any
    for value in node.values():
        if isinstance(value, dict | list):
            _rewrite_node(
                node=value,
                rewrites=rewrites,
                visible_ctes=visible_ctes,
                dialect=dialect,
            )


def _rewrite_relation_slots(
    *,
    select_payload: dict[str, Any],
    rewrites: tuple[SqlRelationRewrite, ...],
    visible_ctes: frozenset[str],
    dialect: str,
) -> None:
    from_payload: Any = select_payload.get(POLYGLOT_FROM_KEY)
    if isinstance(from_payload, dict):
        expressions: Any = from_payload.get(POLYGLOT_EXPRESSIONS_KEY)
        if isinstance(expressions, list):
            from_payload[POLYGLOT_EXPRESSIONS_KEY] = _rewritten_relations(
                relations=expressions,
                rewrites=rewrites,
                visible_ctes=visible_ctes,
                dialect=dialect,
            )
    joins: Any = select_payload.get(POLYGLOT_JOINS_KEY)
    if isinstance(joins, list):
        join: Any
        for join in joins:
            if isinstance(join, dict):
                relation: Any = join.get(POLYGLOT_ALIAS_VALUE_KEY)
                join[POLYGLOT_ALIAS_VALUE_KEY] = _rewritten_relation(
                    relation=relation,
                    rewrites=rewrites,
                    visible_ctes=visible_ctes,
                    dialect=dialect,
                )


def _rewritten_relations(
    *,
    relations: list[Any],
    rewrites: tuple[SqlRelationRewrite, ...],
    visible_ctes: frozenset[str],
    dialect: str,
) -> list[Any]:
    rewritten_relations: list[Any] = []
    relation: Any
    for relation in relations:
        rewritten_relations.append(
            _rewritten_relation(
                relation=relation,
                rewrites=rewrites,
                visible_ctes=visible_ctes,
                dialect=dialect,
            )
        )
    return rewritten_relations


def _rewritten_relation(
    *,
    relation: Any,
    rewrites: tuple[SqlRelationRewrite, ...],
    visible_ctes: frozenset[str],
    dialect: str,
) -> Any:
    if not isinstance(relation, dict):
        return relation
    table_payload: Any = relation.get(POLYGLOT_TABLE_KEY)
    if not isinstance(table_payload, dict):
        _rewrite_node(
            node=relation,
            rewrites=rewrites,
            visible_ctes=visible_ctes,
            dialect=dialect,
        )
        return relation
    table_name: str | None = _identifier_name(table_payload.get(POLYGLOT_NAME_KEY))
    database: str | None = _identifier_name(table_payload.get(POLYGLOT_SCHEMA_KEY))
    if table_name is None or (database is None and table_name in visible_ctes):
        return relation
    rewrite: SqlRelationRewrite | None = _matching_rewrite(
        rewrites=rewrites,
        table_name=table_name,
        database=database,
    )
    if rewrite is None:
        return relation
    replacement: dict[str, Any] = deepcopy(
        _parse_relation(target=rewrite.target_relation, dialect=dialect)[0]
    )
    if rewrite.preserve_source_database:
        _transfer_relation_database(source=table_payload, replacement=replacement)
    _transfer_relation_alias(source=table_payload, replacement=replacement)
    return replacement


def _matching_rewrite(
    *,
    rewrites: tuple[SqlRelationRewrite, ...],
    table_name: str,
    database: str | None,
) -> SqlRelationRewrite | None:
    rewrite: SqlRelationRewrite
    for rewrite in rewrites:
        if rewrite.source_name != table_name:
            continue
        if rewrite.source_databases is None or database in rewrite.source_databases:
            return rewrite
    return None


def _transfer_relation_alias(*, source: dict[str, Any], replacement: dict[str, Any]) -> None:
    replacement_payload: Any = next(iter(replacement.values()), None)
    if not isinstance(replacement_payload, dict):
        raise SqlAnalysisError("Replacement relation has an invalid shape")
    field: str
    for field in _RELATION_ALIAS_FIELDS:
        if field in source:
            replacement_payload[field] = deepcopy(source[field])


def _transfer_relation_database(*, source: dict[str, Any], replacement: dict[str, Any]) -> None:
    table_payload: Any = replacement.get(POLYGLOT_TABLE_KEY)
    if not isinstance(table_payload, dict):
        raise SqlAnalysisError("Database preservation requires a table replacement")
    table_payload[POLYGLOT_SCHEMA_KEY] = deepcopy(source.get(POLYGLOT_SCHEMA_KEY))


def _parenthesized_and(*, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        POLYGLOT_AND_KEY: {
            POLYGLOT_LEFT_KEY: _parenthesized(left),
            "left_comments": [],
            "operator_comments": [],
            POLYGLOT_RIGHT_KEY: _parenthesized(right),
            "trailing_comments": [],
        }
    }


def _parenthesized(predicate: dict[str, Any]) -> dict[str, Any]:
    return {
        POLYGLOT_PAREN_KEY: {
            POLYGLOT_ALIAS_VALUE_KEY: predicate,
            "trailing_comments": [],
        }
    }


def _parse_cte(*, named_query: SqlNamedQuery, dialect: str) -> dict[str, Any]:
    tree: dict[str, Any] = parse_sql_tree(
        sql=f"WITH {named_query.name} AS ({named_query.query}) SELECT 1",
        dialect=dialect,
    )
    ctes: list[Any] = _select_ctes(get_select_payload(tree))
    if len(ctes) != 1 or not isinstance(ctes[0], dict):
        raise SqlAnalysisError(f"Replay CTE '{named_query.name}' could not be parsed")
    if _identifier_name(ctes[0].get(POLYGLOT_ALIAS_KEY)) != named_query.name:
        raise SqlAnalysisError(f"Replay CTE '{named_query.name}' has an invalid name")
    return ctes[0]


def _select_ctes(select_payload: dict[str, Any]) -> list[Any]:
    with_payload: Any = select_payload.get(POLYGLOT_WITH_KEY)
    if not isinstance(with_payload, dict):
        return []
    ctes: Any = with_payload.get(POLYGLOT_CTES_KEY)
    return ctes if isinstance(ctes, list) else []


def _cte_names(ctes: Iterable[Any]) -> frozenset[str]:
    names: set[str] = set()
    cte: Any
    for cte in ctes:
        if isinstance(cte, dict):
            name: str | None = _identifier_name(cte.get(POLYGLOT_ALIAS_KEY))
            if name is not None:
                names.add(name)
    return frozenset(names)


def _identifier_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    name: Any = payload.get(POLYGLOT_NAME_KEY)
    return name if isinstance(name, str) else None
