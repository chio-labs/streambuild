"""Assemble a neutral catalog snapshot from ClickHouse system tables."""

from collections.abc import Mapping
from hashlib import sha256

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterQueryResult,
    AdapterRefreshState,
    AdapterTable,
    AdapterView,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapters.clickhouse._helpers.catalog_parsing import (
    normalize_catalog_query,
    normalize_partition_key,
    parse_catalog_ddl_details,
    parse_catalog_engine,
    parse_catalog_query_details,
    parse_catalog_relation_identities,
    parse_catalog_target_identity,
    parse_sorting_key,
)
from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_DEFAULT_INDEX_GRANULARITY,
    CLICKHOUSE_KAFKA_ENGINE,
    CLICKHOUSE_MATERIALIZED_VIEW_ENGINE,
    CLICKHOUSE_VIEW_ENGINE,
    CLICKHOUSE_ZERO_UUID,
    EMPTY_DEFAULT_EXPRESSIONS,
)
from streambuild.adapters.clickhouse.main.database_scoped_consumer_group import (
    database_scoped_consumer_group,
)
from streambuild.adapters.clickhouse.models import (
    ClickHouseCatalogColumnRow,
    ClickHouseCatalogRelationRow,
)
from streambuild.compiler.sql_analysis.models import SqlRelationIdentity


def load_clickhouse_catalog(
    *,
    connection: AdapterConnection,
    adapter_identity: AdapterIdentity,
    database: str,
) -> CatalogSnapshot:
    """Load one fixed-query ClickHouse catalog snapshot."""

    quoted_database: str = quote_clickhouse_sql_string(database)
    timezone_rows: tuple[tuple[object, ...], ...] = connection.query("SELECT timezone()").rows
    if not timezone_rows:
        raise AdapterResultError("Could not determine ClickHouse server timezone")
    relation_rows: tuple[ClickHouseCatalogRelationRow, ...] = connection.query_many(
        statement=(
            "SELECT name, engine, sorting_key, partition_key, create_table_query, as_select, "
            "toString(uuid) AS uuid "
            f"FROM system.tables WHERE database = {quoted_database} ORDER BY name"
        ),
        decode=_decode_relation_row,
    )
    column_rows: tuple[ClickHouseCatalogColumnRow, ...] = connection.query_many(
        statement=(
            "SELECT table, name, type, default_expression FROM system.columns "
            f"WHERE database = {quoted_database} ORDER BY table, position"
        ),
        decode=_decode_column_row,
    )
    columns_by_relation: dict[str, list[CatalogColumn]] = {}
    column_row: ClickHouseCatalogColumnRow
    for column_row in column_rows:
        columns_by_relation.setdefault(column_row.table_name, []).append(
            CatalogColumn(
                name=column_row.name,
                type=column_row.type,
                default_expression=column_row.default_expression,
            )
        )
    return CatalogSnapshot(
        identity=CatalogIdentity(adapter=adapter_identity, database=database),
        warehouse_timezone=str(timezone_rows[0][0]),
        relations=tuple(
            _build_catalog_relation(
                row=row,
                columns=tuple(columns_by_relation.get(row.name, ())),
            )
            for row in relation_rows
        ),
    )


def load_clickhouse_external_dependants(
    *, connection: AdapterConnection, database: str, relation_names: tuple[str, ...]
) -> tuple[str, ...]:
    """Scan all user databases for relations that depend on target-owned names."""

    owned: frozenset[tuple[str, str]] = frozenset((database, name) for name in relation_names)
    result: AdapterQueryResult = connection.query(
        "SELECT database, name, as_select, create_table_query FROM system.tables "
        "WHERE database NOT IN ('system', 'information_schema', 'INFORMATION_SCHEMA') "
        "AND (as_select != '' OR create_table_query != '') ORDER BY database, name"
    )
    blocked: list[str] = []
    for row in result.rows:
        relation_database: str = str(row[0])
        relation_name: str = str(row[1])
        if (relation_database, relation_name) in owned:
            continue
        sources: tuple[SqlRelationIdentity, ...] = parse_catalog_relation_identities(str(row[2]))
        target: SqlRelationIdentity | None = parse_catalog_target_identity(str(row[3]))
        dependencies: tuple[SqlRelationIdentity, ...] = (
            sources if target is None else (*sources, target)
        )
        if any(
            (dependency.database or relation_database, dependency.name) in owned
            for dependency in dependencies
        ):
            blocked.append(f"{relation_database}.{relation_name}")
    return tuple(blocked)


def _build_catalog_relation(
    *,
    row: ClickHouseCatalogRelationRow,
    columns: tuple[CatalogColumn, ...],
) -> CatalogRelation:
    ttl: str | None
    settings: tuple[tuple[str, str], ...]
    target_relation_name: str | None
    ttl, settings, target_relation_name = parse_catalog_ddl_details(row.create_table_query)
    query_sql: str | None
    source_relation_names: tuple[str, ...]
    stable_binding_name: str | None
    query_sql, source_relation_names, stable_binding_name = parse_catalog_query_details(
        engine=row.engine,
        value=row.as_select,
    )
    return CatalogRelation(
        name=row.name,
        engine=row.engine,
        columns=columns,
        full_engine=parse_catalog_engine(row.create_table_query),
        order_by=parse_sorting_key(row.sorting_key),
        partition_by=normalize_partition_key(row.partition_key),
        ttl=ttl,
        settings=settings,
        definition_sql=row.create_table_query,
        query_sql=query_sql,
        source_relation_names=source_relation_names,
        target_relation_name=target_relation_name,
        stable_binding_name=stable_binding_name,
        ownership_generation=_ownership_generation(
            uuid=row.uuid,
            definition_sql=row.create_table_query,
        ),
    )


def _decode_relation_row(row: Mapping[str, object]) -> ClickHouseCatalogRelationRow:
    return ClickHouseCatalogRelationRow(
        name=str(row["name"]),
        engine=str(row["engine"]),
        sorting_key=str(row["sorting_key"]),
        partition_key=str(row["partition_key"]),
        create_table_query=str(row["create_table_query"]),
        as_select=str(row["as_select"]),
        uuid=str(row["uuid"]),
    )


def _decode_column_row(row: Mapping[str, object]) -> ClickHouseCatalogColumnRow:
    return ClickHouseCatalogColumnRow(
        table_name=str(row["table"]),
        name=str(row["name"]),
        type=str(row["type"]),
        default_expression=(
            None
            if row["default_expression"] in EMPTY_DEFAULT_EXPRESSIONS
            else str(row["default_expression"])
        ),
    )


def quote_clickhouse_sql_string(value: str) -> str:
    """Quote one ClickHouse string literal without changing its value."""

    escaped_value: str = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped_value}'"


def _ownership_generation(*, uuid: str, definition_sql: str) -> str:
    if uuid and uuid != CLICKHOUSE_ZERO_UUID:
        return uuid
    return sha256(definition_sql.encode()).hexdigest()


def clickhouse_catalog_resource_matches(
    *,
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView,
    relation: CatalogRelation,
    database: str,
) -> bool:
    """Compare every structural field available through the ClickHouse catalog."""

    expected_columns: tuple[tuple[str, str, str | None], ...] = (
        tuple((column.name, column.type, column.default_expression) for column in resource.columns)
        if isinstance(resource, (AdapterManagedSource, AdapterTable))
        else ()
    )
    actual_columns: tuple[tuple[str, str, str | None], ...] = tuple(
        (column.name, column.type, column.default_expression) for column in relation.columns
    )
    if expected_columns and expected_columns != actual_columns:
        return False
    if isinstance(resource, AdapterManagedSource):
        expected_settings: dict[str, str] = {
            "kafka_broker_list": resource.broker_list,
            "kafka_topic_list": resource.topic,
            "kafka_group_name": database_scoped_consumer_group(
                consumer_group=resource.consumer_group,
                database=database,
            ),
            "kafka_format": resource.format,
            **dict(resource.settings),
        }
        actual_settings: dict[str, str] = {
            name: value.strip().strip("'") for name, value in relation.settings
        }
        return relation.engine == CLICKHOUSE_KAFKA_ENGINE and actual_settings == expected_settings
    if isinstance(resource, AdapterTable):
        expected_engine: str = resource.engine.strip().removesuffix("()")
        actual_settings: tuple[tuple[str, str], ...] = tuple(
            setting
            for setting in relation.settings
            if setting != CLICKHOUSE_DEFAULT_INDEX_GRANULARITY or resource.settings
        )
        return (
            relation.engine == expected_engine
            and resource.order_by == relation.order_by
            and resource.partition_by == relation.partition_by
            and resource.ttl == relation.ttl
            and resource.settings == actual_settings
        )
    expected_query: str | None = normalize_catalog_query(
        resource.database_template.replace(
            f"{ADAPTER_DATABASE_PLACEHOLDER}.",
            f"{database}.",
        )
    )
    if isinstance(resource, AdapterMaterializedView):
        return (
            relation.engine == CLICKHOUSE_MATERIALIZED_VIEW_ENGINE
            and relation.source_relation_name == resource.source_relation_name
            and relation.target_relation_name == resource.target_relation_name
            and relation.query_sql == expected_query
        )
    return relation.engine == CLICKHOUSE_VIEW_ENGINE and relation.query_sql == expected_query


def load_clickhouse_refresh_states(
    *, connection: AdapterConnection, database: str
) -> tuple[AdapterRefreshState, ...]:
    """Report the refresh state of every scheduled relation in one database."""

    escaped_database: str = database.replace("\\", "\\\\").replace("'", "\\'")
    result: AdapterQueryResult = connection.query(
        "SELECT view, status, last_refresh_time, last_success_time, next_refresh_time, "
        f"exception FROM system.view_refreshes WHERE database = '{escaped_database}' ORDER BY view"
    )
    return tuple(
        AdapterRefreshState(
            view_name=str(row[0]),
            status=str(row[1]),
            last_refresh_at=_optional_text(row[2]),
            last_success_at=_optional_text(row[3]),
            next_refresh_at=_optional_text(row[4]),
            exception=_optional_text(row[5]),
        )
        for row in result.rows
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text: str = str(value)
    return text or None
