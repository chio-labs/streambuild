"""Apache-2.0: SQLBuild planner/_helpers/scenario/relations.py@7e3b2f854f05."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

import polyglot_sql

from streambuild.compiler.sql_analysis.constants import (
    MODEL_REFERENCE_FUNCTION,
    POLYGLOT_ALIAS_KEY,
    POLYGLOT_ALIAS_VALUE_KEY,
    POLYGLOT_ARGUMENTS_KEY,
    POLYGLOT_COLUMN_KEY,
    POLYGLOT_EQ_KEY,
    POLYGLOT_EXPRESSIONS_KEY,
    POLYGLOT_FROM_KEY,
    POLYGLOT_FUNCTION_KEY,
    POLYGLOT_JOINS_KEY,
    POLYGLOT_LEFT_KEY,
    POLYGLOT_LITERAL_KEY,
    POLYGLOT_NAME_KEY,
    POLYGLOT_RIGHT_KEY,
    POLYGLOT_SCHEMA_KEY,
    POLYGLOT_SELECT_KEY,
    POLYGLOT_TABLE_KEY,
    POLYGLOT_VALUE_KEY,
    POLYGLOT_WITH_KEY,
    REFERENCE_TYPE_KEYWORD,
    REFERENCE_WITH_TYPE_ARGUMENT_COUNT,
    SOURCE_REFERENCE_FUNCTION,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import SqlReference, SqlResolvedQuery
from streambuild.compiler.sql_analysis.types import RefType, SqlRelationType

type _ReferenceIdentity = tuple[SqlRelationType, str, RefType | None]
type _CachedRelation = tuple[dict[str, Any], str]
type _RelationCache = dict[str, _CachedRelation]


def build_validated_relation_rewrite(
    *,
    sql: str,
    dialect: str,
    references: tuple[SqlReference, ...],
    resolver: Mapping[str, str],
    relation_cache: _RelationCache,
) -> tuple[dict[str, str], _RelationCache]:
    """Validate one relation-only rewrite through Polyglot without exposing its AST."""

    tree: dict[str, Any] = parse_sql_tree(sql=sql, dialect=dialect)
    actual_identities: tuple[_ReferenceIdentity, ...] = ()
    actual_identities, relation_cache = _rewrite_tree(
        node=tree,
        dialect=dialect,
        resolver=resolver,
        actual_identities=actual_identities,
        relation_cache=relation_cache,
    )
    _validate_reference_identities(references=references, actual_identities=actual_identities)
    if references:
        _ = generate_sql_tree(tree=tree, dialect=dialect)
    canonical_relation_by_target: dict[str, str] = {
        target: cached_relation[1] for target, cached_relation in relation_cache.items()
    }
    return canonical_relation_by_target, relation_cache


def parse_sql_trees(*, sql: str, dialect: str) -> tuple[dict[str, Any], ...]:
    """Parse SQL into private serialized Polyglot trees."""

    try:
        expressions: list[Any] = polyglot_sql.parse(sql, dialect=dialect)
        return tuple(expression.to_dict() for expression in expressions)
    except Exception as error:
        raise SqlAnalysisError(f"SQL could not be parsed with Polyglot: {error}") from None


def parse_sql_tree(*, sql: str, dialect: str) -> dict[str, Any]:
    """Parse exactly one SQL expression into a private serialized tree."""

    try:
        expression: Any = polyglot_sql.parse_one(sql, dialect=dialect)
        return expression.to_dict()
    except Exception as error:
        raise SqlAnalysisError(f"SQL could not be parsed with Polyglot: {error}") from None


def analyze_query_facts(*, sql: str, dialect: str) -> dict[str, Any]:
    """Return one private compact Polyglot query-analysis payload."""

    try:
        result: Any = polyglot_sql.analyze_query(sql, {"dialect": dialect})
    except Exception as error:
        raise SqlAnalysisError(f"SQL could not be analyzed with Polyglot: {error}") from None
    if not isinstance(result, dict):
        raise SqlAnalysisError("Polyglot query analysis did not return a mapping")
    return result


def generate_sql_tree(*, tree: dict[str, Any], dialect: str, pretty: bool = False) -> str:
    """Generate exactly one SQL expression from a private serialized tree."""

    try:
        generated: list[str] = polyglot_sql.generate(tree, dialect=dialect, pretty=pretty)
    except Exception as error:
        raise SqlAnalysisError(f"SQL could not be generated with Polyglot: {error}") from None
    if len(generated) != 1:
        raise SqlAnalysisError(
            f"Polyglot generated {len(generated)} statements where exactly one was required"
        )
    return generated[0]


def build_resolved_query(
    *,
    tree: dict[str, Any],
    dialect: str,
    references: tuple[SqlReference, ...],
    resolver: Mapping[str, str],
    relation_cache: _RelationCache,
    database_placeholder: str,
) -> tuple[SqlResolvedQuery, _RelationCache]:
    """Resolve and qualify one previously parsed model tree without reparsing it."""

    resolved_tree: dict[str, Any] = deepcopy(tree)
    actual_identities: tuple[_ReferenceIdentity, ...] = ()
    actual_identities, relation_cache = _rewrite_tree(
        node=resolved_tree,
        dialect=dialect,
        resolver=resolver,
        actual_identities=actual_identities,
        relation_cache=relation_cache,
    )
    _validate_reference_identities(references=references, actual_identities=actual_identities)
    canonical_sql: str = generate_sql_tree(tree=resolved_tree, dialect=dialect, pretty=True)
    _reject_reserved_database_placeholder(
        canonical_sql=canonical_sql,
        database_placeholder=database_placeholder,
    )
    database_template_tree: dict[str, Any] = deepcopy(resolved_tree)
    qualify_query_relations(tree=database_template_tree, database=database_placeholder)
    return (
        SqlResolvedQuery(
            canonical_sql=canonical_sql,
            database_template=generate_sql_tree(
                tree=database_template_tree,
                dialect=dialect,
                pretty=True,
            ),
        ),
        relation_cache,
    )


def canonical_query_with_database_template(
    *, sql: str, dialect: str, database_placeholder: str
) -> SqlResolvedQuery:
    """Generate canonical and database-template forms of one non-model query."""

    tree: dict[str, Any] = parse_sql_tree(sql=sql, dialect=dialect)
    canonical_sql: str = generate_sql_tree(tree=tree, dialect=dialect, pretty=True)
    _reject_reserved_database_placeholder(
        canonical_sql=canonical_sql,
        database_placeholder=database_placeholder,
    )
    database_template_tree: dict[str, Any] = deepcopy(tree)
    qualify_query_relations(tree=database_template_tree, database=database_placeholder)
    return SqlResolvedQuery(
        canonical_sql=canonical_sql,
        database_template=generate_sql_tree(
            tree=database_template_tree,
            dialect=dialect,
            pretty=True,
        ),
    )


def _reject_reserved_database_placeholder(*, canonical_sql: str, database_placeholder: str) -> None:
    if database_placeholder in canonical_sql:
        raise SqlAnalysisError("SQL contains the reserved adapter database placeholder")


def _rewrite_tree(
    *,
    node: Any,
    dialect: str,
    resolver: Mapping[str, str],
    actual_identities: tuple[_ReferenceIdentity, ...],
    relation_cache: _RelationCache,
) -> tuple[tuple[_ReferenceIdentity, ...], _RelationCache]:
    if isinstance(node, dict):
        from_clause: Any = node.get(POLYGLOT_FROM_KEY)
        if isinstance(from_clause, dict):
            expressions: Any = from_clause.get(POLYGLOT_EXPRESSIONS_KEY)
            if isinstance(expressions, list):
                for index, expression in enumerate(expressions):
                    replacement: dict[str, Any] | None
                    replacement, actual_identities, relation_cache = _replacement(
                        expression=expression,
                        dialect=dialect,
                        resolver=resolver,
                        identities=actual_identities,
                        relation_cache=relation_cache,
                    )
                    if replacement is not None:
                        expressions[index] = replacement
        joins: Any = node.get(POLYGLOT_JOINS_KEY)
        if isinstance(joins, list):
            join: Any
            for join in joins:
                if isinstance(join, dict):
                    replacement, actual_identities, relation_cache = _replacement(
                        expression=join.get(POLYGLOT_ALIAS_VALUE_KEY),
                        dialect=dialect,
                        resolver=resolver,
                        identities=actual_identities,
                        relation_cache=relation_cache,
                    )
                    if replacement is not None:
                        join[POLYGLOT_ALIAS_VALUE_KEY] = replacement
        value: Any
        for value in tuple(node.values()):
            if isinstance(value, dict | list):
                actual_identities, relation_cache = _rewrite_tree(
                    node=value,
                    dialect=dialect,
                    resolver=resolver,
                    actual_identities=actual_identities,
                    relation_cache=relation_cache,
                )
    elif isinstance(node, list):
        item: Any
        for item in node:
            if isinstance(item, dict | list):
                actual_identities, relation_cache = _rewrite_tree(
                    node=item,
                    dialect=dialect,
                    resolver=resolver,
                    actual_identities=actual_identities,
                    relation_cache=relation_cache,
                )
    return actual_identities, relation_cache


def _replacement(
    *,
    expression: Any,
    dialect: str,
    resolver: Mapping[str, str],
    identities: tuple[_ReferenceIdentity, ...],
    relation_cache: _RelationCache,
) -> tuple[
    dict[str, Any] | None,
    tuple[_ReferenceIdentity, ...],
    _RelationCache,
]:
    if not isinstance(expression, dict):
        return None, identities, relation_cache
    alias_payload: Any = expression.get(POLYGLOT_ALIAS_KEY)
    if isinstance(alias_payload, dict):
        inner: dict[str, Any] | None
        inner, identities, relation_cache = _replacement(
            expression=alias_payload.get(POLYGLOT_ALIAS_VALUE_KEY),
            dialect=dialect,
            resolver=resolver,
            identities=identities,
            relation_cache=relation_cache,
        )
        if inner is None:
            return None, identities, relation_cache
        alias_payload[POLYGLOT_ALIAS_VALUE_KEY] = inner
        return expression, identities, relation_cache
    identity: _ReferenceIdentity | None = _reference_identity(expression)
    if identity is None:
        return None, identities, relation_cache
    updated_identities: tuple[_ReferenceIdentity, ...] = (*identities, identity)
    if identity[1] not in resolver:
        raise SqlAnalysisError(f"Unresolved ref: {identity[1]}")
    target: str = resolver[identity[1]]
    cached_relation: _CachedRelation | None = relation_cache.get(target)
    if cached_relation is None:
        cached_relation = _parse_relation(target=target, dialect=dialect)
        relation_cache = {**relation_cache, target: cached_relation}
    return deepcopy(cached_relation[0]), updated_identities, relation_cache


def _reference_identity(expression: dict[str, Any]) -> _ReferenceIdentity | None:
    function_payload: Any = expression.get(POLYGLOT_FUNCTION_KEY)
    if not isinstance(function_payload, dict):
        return None
    function_name: str = str(function_payload.get(POLYGLOT_NAME_KEY, ""))
    if function_name not in {SOURCE_REFERENCE_FUNCTION, MODEL_REFERENCE_FUNCTION}:
        return None
    arguments: Any = function_payload.get(POLYGLOT_ARGUMENTS_KEY)
    if not isinstance(arguments, list) or not arguments:
        return None
    name: str | None = _scalar_name(arguments[0])
    if name is None:
        return None
    relation_type: SqlRelationType = (
        SqlRelationType.SOURCE
        if function_name == SOURCE_REFERENCE_FUNCTION
        else SqlRelationType.REF
    )
    ref_type: RefType | None = None
    if (
        len(arguments) == REFERENCE_WITH_TYPE_ARGUMENT_COUNT
        and relation_type == SqlRelationType.REF
    ):
        ref_type = _ast_ref_type(arguments[1])
    return relation_type, name, ref_type


def _ast_ref_type(argument: Any) -> RefType | None:
    if not isinstance(argument, dict):
        return None
    equality: Any = argument.get(POLYGLOT_EQ_KEY)
    if not isinstance(equality, dict):
        return None
    keyword: str | None = _scalar_name(equality.get(POLYGLOT_LEFT_KEY))
    value: str | None = _scalar_name(equality.get(POLYGLOT_RIGHT_KEY))
    if keyword != REFERENCE_TYPE_KEYWORD or value not in {RefType.REFERENCE, RefType.MUTABLE}:
        return None
    return RefType(value)


def _scalar_name(argument: Any) -> str | None:
    if not isinstance(argument, dict):
        return None
    column: Any = argument.get(POLYGLOT_COLUMN_KEY)
    if isinstance(column, dict):
        name_payload: Any = column.get(POLYGLOT_NAME_KEY)
        if isinstance(name_payload, dict):
            name: Any = name_payload.get(POLYGLOT_NAME_KEY)
            return name if isinstance(name, str) else None
    literal: Any = argument.get(POLYGLOT_LITERAL_KEY)
    if isinstance(literal, dict):
        value: Any = literal.get(POLYGLOT_VALUE_KEY)
        return value if isinstance(value, str) else None
    return None


def _parse_relation(*, target: str, dialect: str) -> _CachedRelation:
    tree: dict[str, Any] = parse_sql_tree(sql=f"SELECT * FROM {target}", dialect=dialect)
    select_payload: Any = tree.get(POLYGLOT_SELECT_KEY)
    if not isinstance(select_payload, dict):
        raise SqlAnalysisError(f"Resolved relation '{target}' is not a valid SQL relation")
    from_payload: Any = select_payload.get(POLYGLOT_FROM_KEY)
    if not isinstance(from_payload, dict):
        raise SqlAnalysisError(f"Resolved relation '{target}' is not a valid SQL relation")
    expressions: Any = from_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list) or len(expressions) != 1:
        raise SqlAnalysisError(f"Resolved relation '{target}' is not a valid SQL relation")
    relation: Any = expressions[0]
    if not isinstance(relation, dict):
        raise SqlAnalysisError(f"Resolved relation '{target}' is not a valid SQL relation")
    relation_payload: Any = next(iter(relation.values()), None)
    if POLYGLOT_ALIAS_KEY in relation or (
        isinstance(relation_payload, dict)
        and cast(dict[str, Any], relation_payload).get(POLYGLOT_ALIAS_KEY) is not None
    ):
        raise SqlAnalysisError(f"Resolved relation '{target}' must not define its own alias")
    canonical_relation: str = generate_sql_tree(tree=relation, dialect=dialect)
    return relation, canonical_relation


def _validate_reference_identities(
    *, references: tuple[SqlReference, ...], actual_identities: tuple[_ReferenceIdentity, ...]
) -> None:
    expected_identities: tuple[_ReferenceIdentity, ...] = tuple(
        (SqlRelationType(reference.relation_type), reference.name, reference.ref_type)
        for reference in references
    )
    if Counter(actual_identities) != Counter(expected_identities):
        raise SqlAnalysisError(
            "__source(...) and __ref(...) calls are valid only in FROM or JOIN relation positions"
        )


def qualify_query_relations(*, tree: dict[str, Any], database: str) -> None:
    """Qualify physical table nodes while preserving CTE relation identities."""

    _qualify_node(node=tree, database=database, visible_ctes=frozenset())


def _qualify_node(*, node: Any, database: str, visible_ctes: frozenset[str]) -> None:
    if isinstance(node, list):
        item: Any
        for item in node:
            _qualify_node(node=item, database=database, visible_ctes=visible_ctes)
        return
    if not isinstance(node, dict):
        return
    select_payload: Any = node.get(POLYGLOT_SELECT_KEY)
    if isinstance(select_payload, dict):
        local_ctes: frozenset[str] = _select_cte_names(select_payload)
        _qualify_node(
            node=select_payload,
            database=database,
            visible_ctes=visible_ctes | local_ctes,
        )
        return
    table_payload: Any = node.get(POLYGLOT_TABLE_KEY)
    if isinstance(table_payload, dict) and POLYGLOT_SCHEMA_KEY in table_payload:
        table_name: str | None = _identifier_name(table_payload.get(POLYGLOT_NAME_KEY))
        if (
            table_name is not None
            and table_name not in visible_ctes
            and table_payload.get(POLYGLOT_SCHEMA_KEY) is None
        ):
            table_payload[POLYGLOT_SCHEMA_KEY] = _identifier(database)
        return
    value: Any
    for value in node.values():
        if isinstance(value, dict | list):
            _qualify_node(node=value, database=database, visible_ctes=visible_ctes)


def _select_cte_names(select_payload: dict[str, Any]) -> frozenset[str]:
    with_payload: Any = select_payload.get(POLYGLOT_WITH_KEY)
    if not isinstance(with_payload, dict):
        return frozenset()
    ctes: Any = with_payload.get("ctes")
    if not isinstance(ctes, list):
        return frozenset()
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


def _identifier(name: str) -> dict[str, Any]:
    return {POLYGLOT_NAME_KEY: name, "quoted": False, "trailing_comments": []}
