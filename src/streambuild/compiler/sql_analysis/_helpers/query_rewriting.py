"""Apache-2.0: SQLBuild planner/_helpers/scenario/relations.py@7e3b2f854f05."""

from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from streambuild.compiler.sql_analysis._helpers.polyglot import (
    _parse_relation,
    generate_sql_tree,
    parse_sql_tree,
)
from streambuild.compiler.sql_analysis.constants import (
    POLYGLOT_ALIAS_KEY,
    POLYGLOT_ALIAS_VALUE_KEY,
    POLYGLOT_AND_KEY,
    POLYGLOT_CTES_KEY,
    POLYGLOT_EQ_KEY,
    POLYGLOT_EXPRESSIONS_KEY,
    POLYGLOT_FROM_KEY,
    POLYGLOT_JOINS_KEY,
    POLYGLOT_LEFT_KEY,
    POLYGLOT_NAME_KEY,
    POLYGLOT_PAREN_KEY,
    POLYGLOT_RIGHT_KEY,
    POLYGLOT_SCHEMA_KEY,
    POLYGLOT_SELECT_KEY,
    POLYGLOT_STAR_KEY,
    POLYGLOT_TABLE_KEY,
    POLYGLOT_WHERE_CLAUSE_KEY,
    POLYGLOT_WITH_KEY,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.models import (
    SqlCatalogAnalysis,
    SqlNamedQuery,
    SqlRelationIdentity,
    SqlRelationRewrite,
)

_RELATION_ALIAS_FIELDS: tuple[str, ...] = (
    POLYGLOT_ALIAS_KEY,
    "alias_explicit_as",
    "alias_keyword",
    "column_aliases",
    "trailing_comments",
)
_CREATE_TABLE_KEY: str = "create_table"
_CREATE_VIEW_KEY: str = "create_view"
_MERGE_TREE_TTL_KEY: str = "merge_tree_t_t_l"
_PROPERTIES_KEY: str = "properties"
_QUERY_KEY: str = "query"
_SETTINGS_PROPERTY_KEY: str = "settings_property"
_TO_TABLE_KEY: str = "to_table"
_DIRECT_BINDING_TRANSFORM_KEYS: tuple[str, ...] = (
    POLYGLOT_WITH_KEY,
    POLYGLOT_WHERE_CLAUSE_KEY,
    "group_by",
    "having",
    "qualify",
    "order_by",
    "distribute_by",
    "cluster_by",
    "sort_by",
    "limit",
    "offset",
    "fetch",
    "distinct_on",
    "top",
    "sample",
    "windows",
    "connect",
    "into",
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


def analyze_catalog_tree(*, tree: dict[str, Any], dialect: str) -> SqlCatalogAnalysis:
    """Return canonical query and ClickHouse catalog facts from one parsed statement."""

    canonical_sql: str = generate_sql_tree(tree=tree, dialect=dialect)
    create_table: Any = tree.get(_CREATE_TABLE_KEY)
    if isinstance(create_table, dict):
        ttl: str | None
        settings: tuple[tuple[str, str], ...]
        ttl, settings = _table_properties(create_table=create_table, dialect=dialect)
        return SqlCatalogAnalysis(
            canonical_sql=canonical_sql,
            query_sql=None,
            first_source=None,
            direct_source=None,
            target_relation=None,
            ttl=ttl,
            settings=settings,
        )
    create_view: Any = tree.get(_CREATE_VIEW_KEY)
    if isinstance(create_view, dict):
        return _view_analysis(
            canonical_sql=canonical_sql,
            create_view=create_view,
            dialect=dialect,
        )
    if _is_query_tree(tree):
        return _query_analysis(canonical_sql=canonical_sql, query_tree=tree)
    raise SqlAnalysisError("Catalog SQL must be a query, CREATE TABLE, or CREATE VIEW statement")


def expression_list(*, tree: dict[str, Any], dialect: str) -> tuple[str, ...]:
    """Return top-level expressions from a synthetic SELECT projection."""

    select_payload: Any = tree.get(POLYGLOT_SELECT_KEY)
    if not isinstance(select_payload, dict):
        raise SqlAnalysisError("Expression list must parse as a SELECT projection")
    expressions: Any = select_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list):
        raise SqlAnalysisError("Expression list has an invalid projection shape")
    if len(expressions) != 1:
        return tuple(generate_sql_tree(tree=item, dialect=dialect) for item in expressions)
    expression: Any = expressions[0]
    if not isinstance(expression, dict):
        raise SqlAnalysisError("Expression list has an invalid projection expression")
    tuple_payload: Any = expression.get("tuple")
    if isinstance(tuple_payload, dict):
        tuple_expressions: Any = tuple_payload.get(POLYGLOT_EXPRESSIONS_KEY)
        if isinstance(tuple_expressions, list):
            return tuple(
                generate_sql_tree(tree=item, dialect=dialect) for item in tuple_expressions
            )
    paren_payload: Any = expression.get(POLYGLOT_PAREN_KEY)
    if isinstance(paren_payload, dict) and isinstance(
        paren_payload.get(POLYGLOT_ALIAS_VALUE_KEY), dict
    ):
        return (
            generate_sql_tree(
                tree=paren_payload[POLYGLOT_ALIAS_VALUE_KEY],
                dialect=dialect,
            ),
        )
    return (generate_sql_tree(tree=expression, dialect=dialect),)


def _view_analysis(
    *, canonical_sql: str, create_view: dict[str, Any], dialect: str
) -> SqlCatalogAnalysis:
    query_tree: Any = create_view.get(_QUERY_KEY)
    if not isinstance(query_tree, dict):
        raise SqlAnalysisError("CREATE VIEW statement lacks an AS query")
    query_sql: str = generate_sql_tree(tree=query_tree, dialect=dialect)
    target_relation: SqlRelationIdentity | None = None
    target_payload: Any = create_view.get(_TO_TABLE_KEY)
    if isinstance(target_payload, dict):
        target_relation = _table_identity(target_payload)
    return SqlCatalogAnalysis(
        canonical_sql=canonical_sql,
        query_sql=query_sql,
        first_source=_first_catalog_relation(node=query_tree, visible_ctes={}),
        direct_source=_direct_relation(query_tree),
        target_relation=target_relation,
        ttl=None,
        settings=(),
    )


def _query_analysis(*, canonical_sql: str, query_tree: dict[str, Any]) -> SqlCatalogAnalysis:
    return SqlCatalogAnalysis(
        canonical_sql=canonical_sql,
        query_sql=canonical_sql,
        first_source=_first_catalog_relation(node=query_tree, visible_ctes={}),
        direct_source=_direct_relation(query_tree),
        target_relation=None,
        ttl=None,
        settings=(),
    )


def _table_properties(
    *, create_table: dict[str, Any], dialect: str
) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    properties: Any = create_table.get(_PROPERTIES_KEY)
    if not isinstance(properties, list):
        return None, ()
    ttl: str | None = None
    settings: tuple[tuple[str, str], ...] = ()
    property_: Any
    for property_ in properties:
        if not isinstance(property_, dict):
            continue
        ttl_payload: Any = property_.get(_MERGE_TREE_TTL_KEY)
        if isinstance(ttl_payload, dict):
            ttl = _ttl_sql(ttl_payload=ttl_payload, dialect=dialect)
        settings_payload: Any = property_.get(_SETTINGS_PROPERTY_KEY)
        if isinstance(settings_payload, dict):
            settings = _settings(settings_payload=settings_payload, dialect=dialect)
    return ttl, settings


def _ttl_sql(*, ttl_payload: dict[str, Any], dialect: str) -> str | None:
    expressions: Any = ttl_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list) or not expressions:
        return None
    return ", ".join(generate_sql_tree(tree=item, dialect=dialect) for item in expressions)


def _settings(*, settings_payload: dict[str, Any], dialect: str) -> tuple[tuple[str, str], ...]:
    expressions: Any = settings_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list):
        return ()
    values: list[tuple[str, str]] = []
    expression: Any
    for expression in expressions:
        equality: Any = expression.get(POLYGLOT_EQ_KEY) if isinstance(expression, dict) else None
        if isinstance(equality, dict):
            values.append(
                (
                    generate_sql_tree(tree=equality[POLYGLOT_LEFT_KEY], dialect=dialect),
                    generate_sql_tree(tree=equality[POLYGLOT_RIGHT_KEY], dialect=dialect),
                )
            )
    return tuple(values)


def _direct_relation(tree: dict[str, Any]) -> SqlRelationIdentity | None:
    select_payload: Any = tree.get(POLYGLOT_SELECT_KEY)
    if not isinstance(select_payload, dict) or not _is_direct_binding_select(select_payload):
        return None
    from_payload: Any = select_payload.get(POLYGLOT_FROM_KEY)
    expressions: Any = (
        from_payload.get(POLYGLOT_EXPRESSIONS_KEY) if isinstance(from_payload, dict) else None
    )
    if not isinstance(expressions, list) or len(expressions) != 1:
        return None
    relation: Any = expressions[0]
    table_payload: Any = relation.get(POLYGLOT_TABLE_KEY) if isinstance(relation, dict) else None
    if not isinstance(table_payload, dict):
        return None
    if table_payload.get("final_") is True or table_payload.get("only") is True:
        return None
    return _table_identity(table_payload)


def _is_direct_binding_select(select_payload: dict[str, Any]) -> bool:
    expressions: Any = select_payload.get(POLYGLOT_EXPRESSIONS_KEY)
    if not isinstance(expressions, list) or len(expressions) != 1:
        return False
    projection: Any = expressions[0]
    star: Any = projection.get(POLYGLOT_STAR_KEY) if isinstance(projection, dict) else None
    if not isinstance(star, dict) or any(
        star.get(key) is not None for key in ("table", "except", "replace", "rename")
    ):
        return False
    joins: Any = select_payload.get(POLYGLOT_JOINS_KEY)
    if isinstance(joins, list) and joins:
        return False
    if select_payload.get("distinct") is True:
        return False
    return not any(select_payload.get(key) for key in _DIRECT_BINDING_TRANSFORM_KEYS)


def _first_catalog_relation(
    *,
    node: Any,
    visible_ctes: dict[str, Any],
    resolving_ctes: frozenset[str] = frozenset(),
) -> SqlRelationIdentity | None:
    if isinstance(node, list):
        item: Any
        for item in node:
            relation: SqlRelationIdentity | None = _first_catalog_relation(
                node=item,
                visible_ctes=visible_ctes,
                resolving_ctes=resolving_ctes,
            )
            if relation is not None:
                return relation
        return None
    if not isinstance(node, dict):
        return None
    select_payload: Any = node.get(POLYGLOT_SELECT_KEY)
    if isinstance(select_payload, dict):
        return _first_select_relation(
            select_payload=select_payload,
            visible_ctes=visible_ctes,
            resolving_ctes=resolving_ctes,
        )
    value: Any
    for value in node.values():
        relation = _first_catalog_relation(
            node=value,
            visible_ctes=visible_ctes,
            resolving_ctes=resolving_ctes,
        )
        if relation is not None:
            return relation
    return None


def _first_select_relation(
    *,
    select_payload: dict[str, Any],
    visible_ctes: dict[str, Any],
    resolving_ctes: frozenset[str],
) -> SqlRelationIdentity | None:
    ctes: list[Any] = _select_ctes(select_payload)
    scoped_ctes: dict[str, Any] = {**visible_ctes, **_cte_bodies(ctes)}
    from_payload: Any = select_payload.get(POLYGLOT_FROM_KEY)
    from_expressions: Any = (
        from_payload.get(POLYGLOT_EXPRESSIONS_KEY) if isinstance(from_payload, dict) else None
    )
    relation: SqlRelationIdentity | None = _first_relation_slot(
        relations=from_expressions,
        visible_ctes=scoped_ctes,
        resolving_ctes=resolving_ctes,
    )
    if relation is not None:
        return relation
    joins: Any = select_payload.get(POLYGLOT_JOINS_KEY)
    if isinstance(joins, list):
        join: Any
        for join in joins:
            target: Any = join.get(POLYGLOT_ALIAS_VALUE_KEY) if isinstance(join, dict) else None
            relation = _first_relation_slot(
                relations=[target],
                visible_ctes=scoped_ctes,
                resolving_ctes=resolving_ctes,
            )
            if relation is not None:
                return relation
    return None


def _first_relation_slot(
    *,
    relations: Any,
    visible_ctes: dict[str, Any],
    resolving_ctes: frozenset[str],
) -> SqlRelationIdentity | None:
    if not isinstance(relations, list):
        return None
    relation: Any
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        table_payload: Any = relation.get(POLYGLOT_TABLE_KEY)
        if isinstance(table_payload, dict):
            identity: SqlRelationIdentity = _table_identity(table_payload)
            if identity.database is not None or identity.name not in visible_ctes:
                return identity
            if identity.name not in resolving_ctes:
                nested: SqlRelationIdentity | None = _first_catalog_relation(
                    node=visible_ctes[identity.name],
                    visible_ctes=visible_ctes,
                    resolving_ctes=resolving_ctes | {identity.name},
                )
                if nested is not None:
                    return nested
            continue
        nested: SqlRelationIdentity | None = _first_catalog_relation(
            node=relation,
            visible_ctes=visible_ctes,
            resolving_ctes=resolving_ctes,
        )
        if nested is not None:
            return nested
    return None


def _cte_bodies(ctes: Iterable[Any]) -> dict[str, Any]:
    bodies: dict[str, Any] = {}
    cte: Any
    for cte in ctes:
        if not isinstance(cte, dict):
            continue
        name: str | None = _identifier_name(cte.get(POLYGLOT_ALIAS_KEY))
        body: Any = cte.get(POLYGLOT_ALIAS_VALUE_KEY)
        if name is not None and isinstance(body, dict):
            bodies[name] = body
    return bodies


def _table_identity(table_payload: dict[str, Any]) -> SqlRelationIdentity:
    name: str | None = _identifier_name(table_payload.get(POLYGLOT_NAME_KEY))
    if name is None:
        raise SqlAnalysisError("Catalog relation lacks a table name")
    return SqlRelationIdentity(
        database=_identifier_name(table_payload.get(POLYGLOT_SCHEMA_KEY)),
        name=name,
    )


def _is_query_tree(tree: dict[str, Any]) -> bool:
    return any(key in tree for key in (POLYGLOT_SELECT_KEY, "union", "intersect", "except"))
