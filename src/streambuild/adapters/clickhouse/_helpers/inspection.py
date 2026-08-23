"""Assemble a neutral catalog snapshot from ClickHouse system tables."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterIdentity,
    AdapterQueryResult,
    AdapterRefreshState,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapters.clickhouse._helpers.catalog_parsing import (
    normalize_partition_key,
    parse_catalog_ddl_details,
    parse_catalog_query_details,
    parse_sorting_key,
)
from streambuild.adapters.clickhouse.constants import EMPTY_DEFAULT_EXPRESSIONS
from streambuild.adapters.clickhouse.models import (
    ClickHouseCatalogColumnRow,
    ClickHouseCatalogRelationRow,
)


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
            "SELECT name, engine, sorting_key, partition_key, create_table_query, as_select "
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
    source_relation_name: str | None
    stable_binding_name: str | None
    query_sql, source_relation_name, stable_binding_name = parse_catalog_query_details(
        engine=row.engine,
        value=row.as_select,
    )
    return CatalogRelation(
        name=row.name,
        engine=row.engine,
        columns=columns,
        order_by=parse_sorting_key(row.sorting_key),
        partition_by=normalize_partition_key(row.partition_key),
        ttl=ttl,
        settings=settings,
        definition_sql=row.create_table_query,
        query_sql=query_sql,
        source_relation_name=source_relation_name,
        target_relation_name=target_relation_name,
        stable_binding_name=stable_binding_name,
    )


def _decode_relation_row(row: Mapping[str, object]) -> ClickHouseCatalogRelationRow:
    return ClickHouseCatalogRelationRow(
        name=str(row["name"]),
        engine=str(row["engine"]),
        sorting_key=str(row["sorting_key"]),
        partition_key=str(row["partition_key"]),
        create_table_query=str(row["create_table_query"]),
        as_select=str(row["as_select"]),
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
