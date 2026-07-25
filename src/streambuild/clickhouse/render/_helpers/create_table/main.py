"""Render CREATE TABLE DDL from desired-state models."""

from streambuild.compiler.shared.models import Column, DesiredTable, TableStorage


def render_create_table_ddl(table: DesiredTable, database: str) -> str:
    """Render CREATE TABLE DDL for a desired table."""

    column_definitions: str = ",\n    ".join(
        _render_column_definition(column) for column in table.spec.columns
    )
    storage: TableStorage = table.spec.storage
    ddl: str = (
        f"CREATE TABLE {database}.{table.name} (\n"
        f"    {column_definitions}\n"
        f") ENGINE = {storage.engine}\n"
        f"ORDER BY ({', '.join(storage.order_by)})"
    )

    if storage.partition_by is not None:
        ddl += f"\nPARTITION BY {storage.partition_by}"

    if storage.ttl is not None:
        ddl += f"\nTTL {storage.ttl}"

    if storage.settings:
        rendered_settings: str = ", ".join(
            f"{setting_name} = {setting_value}"
            for setting_name, setting_value in sorted(storage.settings.items())
        )
        ddl += f"\nSETTINGS {rendered_settings}"

    return ddl


def _render_column_definition(column: Column) -> str:
    """Render a single column definition."""

    if column.default is None:
        return f"{column.name} {column.type}"
    return f"{column.name} {column.type} DEFAULT {column.default}"
