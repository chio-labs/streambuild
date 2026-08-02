"""Render neutral adapter resources as ClickHouse SQL."""

from streambuild.adapter.constants import ADAPTER_DATABASE_PLACEHOLDER, MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterColumn,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterSetDifferenceComparisonRequest,
    AdapterSetDifferenceTarget,
    AdapterStableView,
    AdapterTable,
    AdapterView,
)


def render_clickhouse_ensure_database(database: str) -> str:
    """Render one manually executable ClickHouse database creation statement."""

    return f"CREATE DATABASE IF NOT EXISTS {database};"


def render_clickhouse_resource(
    *,
    resource: (
        AdapterManagedSource
        | AdapterTable
        | AdapterMaterializedView
        | AdapterView
        | AdapterStableView
    ),
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
        return _render_table(resource=resource, database=database, if_not_exists=if_not_exists)
    if isinstance(resource, AdapterMaterializedView):
        return _render_materialized_view(
            resource=resource, database=database, if_not_exists=if_not_exists
        )
    if isinstance(resource, AdapterView):
        return _render_view(resource=resource, database=database, if_not_exists=if_not_exists)
    return _render_stable_view(resource=resource, database=database)


def render_clickhouse_set_difference_comparison(
    *, request: AdapterSetDifferenceComparisonRequest
) -> str:
    """Render bidirectional bag comparisons with explicit NULL-safe equality."""

    if not request.targets:
        raise AdapterCapabilityError("ClickHouse comparison requires at least one target")
    return "\nUNION ALL\n".join(
        f"(\n{_render_set_difference_target(target=target, index=index)}\n)"
        for index, target in enumerate(request.targets)
    )


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


def _render_table(*, resource: AdapterTable, database: str, if_not_exists: bool) -> str:
    column_definitions: str = ",\n    ".join(
        _render_column_definition(column) for column in resource.columns
    )
    ddl: str = (
        f"CREATE TABLE {'IF NOT EXISTS ' if if_not_exists else ''}{database}.{resource.name} (\n"
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


def _render_materialized_view(
    *, resource: AdapterMaterializedView, database: str, if_not_exists: bool
) -> str:
    rendered_query: str = resource.database_template.replace(
        f"{ADAPTER_DATABASE_PLACEHOLDER}.",
        f"{database}.",
    )
    return (
        f"CREATE MATERIALIZED VIEW {'IF NOT EXISTS ' if if_not_exists else ''}"
        f"{database}.{resource.name}\n"
        f"TO {database}.{resource.target_relation_name} AS\n"
        f"{rendered_query}"
    )


def _render_view(*, resource: AdapterView, database: str, if_not_exists: bool) -> str:
    rendered_query: str = resource.database_template.replace(
        f"{ADAPTER_DATABASE_PLACEHOLDER}.",
        f"{database}.",
    )
    return (
        f"CREATE VIEW {'IF NOT EXISTS ' if if_not_exists else ''}{database}.{resource.name} AS\n"
        f"{rendered_query}"
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


def _render_set_difference_target(*, target: AdapterSetDifferenceTarget, index: int) -> str:
    suffix: str = str(index)
    expected_counts_name: str = f"__streambuild_expected_counts_{suffix}"
    actual_counts_name: str = f"__streambuild_actual_counts_{suffix}"
    rendered_ctes: list[str] = [f"{name} AS (\n{query}\n)" for name, query in target.ctes]
    if target.expected_query is not None:
        rendered_ctes.append(
            _render_grouped_counts_cte(
                name=expected_counts_name,
                query=target.expected_query,
                column_names=target.column_names,
            )
        )
    rendered_ctes.append(
        _render_grouped_counts_cte(
            name=actual_counts_name,
            query=target.actual_query,
            column_names=target.column_names,
        )
    )
    comparison_sql: str = _render_unexpected_rows(
        index=index,
        actual_counts_name=actual_counts_name,
        expected_counts_name=expected_counts_name,
        column_names=target.column_names,
        expected_empty=target.expected_query is None,
    )
    if target.expected_query is not None:
        comparison_sql = (
            _render_missing_rows(
                index=index,
                expected_counts_name=expected_counts_name,
                actual_counts_name=actual_counts_name,
                column_names=target.column_names,
            )
            + "\nUNION ALL\n"
            + comparison_sql
        )
    return "WITH\n" + ",\n".join(rendered_ctes) + "\n" + comparison_sql


def _render_grouped_counts_cte(*, name: str, query: str, column_names: tuple[str, ...]) -> str:
    columns: str = ", ".join(column_names)
    return (
        f"{name} AS (\n"
        f"SELECT {columns}, count() AS __streambuild_multiplicity\n"
        f"FROM (\n{query}\n)\n"
        f"GROUP BY {columns}\n)"
    )


def _render_missing_rows(
    *,
    index: int,
    expected_counts_name: str,
    actual_counts_name: str,
    column_names: tuple[str, ...],
) -> str:
    return _render_directional_rows(
        index=index,
        diff_type="missing",
        primary_alias="expected_rows",
        secondary_alias="actual_rows",
        primary_name=expected_counts_name,
        secondary_name=actual_counts_name,
        column_names=column_names,
    )


def _render_unexpected_rows(
    *,
    index: int,
    actual_counts_name: str,
    expected_counts_name: str,
    column_names: tuple[str, ...],
    expected_empty: bool,
) -> str:
    if expected_empty:
        row_values: str = _render_row_values(alias="actual_rows", column_names=column_names)
        return (
            f"SELECT {index} AS _case_index, 'unexpected' AS _diff_type,\n"
            f"       {row_values} AS _row_values,\n"
            "       actual_rows.__streambuild_multiplicity AS _multiplicity\n"
            f"FROM {actual_counts_name} AS actual_rows"
        )
    return _render_directional_rows(
        index=index,
        diff_type="unexpected",
        primary_alias="actual_rows",
        secondary_alias="expected_rows",
        primary_name=actual_counts_name,
        secondary_name=expected_counts_name,
        column_names=column_names,
    )


def _render_directional_rows(
    *,
    index: int,
    diff_type: str,
    primary_alias: str,
    secondary_alias: str,
    primary_name: str,
    secondary_name: str,
    column_names: tuple[str, ...],
) -> str:
    row_values: str = _render_row_values(alias=primary_alias, column_names=column_names)
    join_conditions: str = " AND ".join(
        f"isNotDistinctFrom({primary_alias}.{column}, {secondary_alias}.{column})"
        for column in column_names
    )
    return (
        f"SELECT {index} AS _case_index, '{diff_type}' AS _diff_type,\n"
        f"       {row_values} AS _row_values,\n"
        f"       {primary_alias}.__streambuild_multiplicity - "
        f"ifNull({secondary_alias}.__streambuild_multiplicity, 0) AS _multiplicity\n"
        f"FROM {primary_name} AS {primary_alias}\n"
        f"ALL LEFT JOIN {secondary_name} AS {secondary_alias}\n"
        f"ON {join_conditions}\n"
        f"WHERE {primary_alias}.__streambuild_multiplicity > "
        f"ifNull({secondary_alias}.__streambuild_multiplicity, 0)"
    )


def _render_row_values(*, alias: str, column_names: tuple[str, ...]) -> str:
    values: str = ", ".join(
        f"CAST({alias}.{column} AS Nullable(String))" for column in column_names
    )
    return f"[{values}]"
