"""Render neutral adapter resources as ClickHouse SQL."""

from sqlglot import exp, parse_one

from streambuild.adapter.constants import MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterColumn,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
)


def render_clickhouse_resource(
    *,
    resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
    database: str,
    if_not_exists: bool = False,
) -> str:
    """Render one neutral adapter resource as ClickHouse DDL."""

    if isinstance(resource, AdapterManagedSource):
        if resource.source_kind != MANAGED_SOURCE_KIND_KAFKA:
            raise AdapterCapabilityError(
                f"ClickHouse does not support managed source kind '{resource.source_kind}'"
            )
        return _render_managed_source(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )
    if isinstance(resource, AdapterTable):
        return _render_table(resource=resource, database=database)
    if isinstance(resource, AdapterMaterializedView):
        return _render_materialized_view(resource=resource, database=database)
    return _render_stable_view(resource=resource, database=database)


def _render_managed_source(
    *,
    resource: AdapterManagedSource,
    database: str,
    if_not_exists: bool,
) -> str:
    column_definitions: str = ",\n    ".join(
        _render_column_definition(column) for column in resource.columns
    )
    create_prefix: str = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    consumer_group: str = _database_scoped_consumer_group(
        consumer_group=resource.consumer_group,
        database=database,
    )
    settings: list[str] = [
        f"kafka_broker_list = '{resource.broker_list}'",
        f"kafka_topic_list = '{resource.topic}'",
        f"kafka_group_name = '{consumer_group}'",
        f"kafka_format = '{resource.format}'",
    ]
    setting_name: str
    setting_value: str
    for setting_name, setting_value in resource.settings:
        settings.append(f"{setting_name} = '{setting_value}'")
    return (
        f"{create_prefix} {database}.{resource.name} (\n"
        f"    {column_definitions}\n"
        ") ENGINE = Kafka\n"
        f"SETTINGS {', '.join(settings)}"
    )


def _render_table(*, resource: AdapterTable, database: str) -> str:
    column_definitions: str = ",\n    ".join(
        _render_column_definition(column) for column in resource.columns
    )
    ddl: str = (
        f"CREATE TABLE {database}.{resource.name} (\n"
        f"    {column_definitions}\n"
        f") ENGINE = {resource.engine}\n"
        f"ORDER BY ({', '.join(resource.order_by)})"
    )
    if resource.partition_by is not None:
        ddl += f"\nPARTITION BY {resource.partition_by}"
    if resource.ttl is not None:
        ddl += f"\nTTL {resource.ttl}"
    if resource.settings:
        rendered_settings: str = ", ".join(
            f"{setting_name} = {setting_value}" for setting_name, setting_value in resource.settings
        )
        ddl += f"\nSETTINGS {rendered_settings}"
    return ddl


def _render_materialized_view(*, resource: AdapterMaterializedView, database: str) -> str:
    expression: exp.Expr = parse_one(resource.query, dialect="clickhouse")
    table: exp.Table
    for table in expression.find_all(exp.Table):
        if table.db:
            continue
        table.set("db", exp.to_identifier(database))
    qualified_query: str = expression.sql(dialect="clickhouse", pretty=True)
    return (
        f"CREATE MATERIALIZED VIEW {database}.{resource.name}\n"
        f"TO {database}.{resource.target_relation_name} AS\n"
        f"{qualified_query}"
    )


def _render_stable_view(*, resource: AdapterStableView, database: str) -> str:
    return (
        f"CREATE OR REPLACE VIEW {database}.{resource.name} AS\n"
        f"SELECT * FROM {database}.{resource.target_relation_name}"
    )


def _render_column_definition(column: AdapterColumn) -> str:
    if column.default_expression is None:
        return f"{column.name} {column.type}"
    return f"{column.name} {column.type} DEFAULT {column.default_expression}"


def _database_scoped_consumer_group(*, consumer_group: str, database: str) -> str:
    normalized_database: str = database.replace("-", "_")
    return f"{consumer_group}_{normalized_database}"
