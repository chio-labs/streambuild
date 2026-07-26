"""Render CREATE TABLE DDL for Kafka engine tables."""

from streambuild.compiler.shared.models import Column, DesiredKafkaTable, KafkaTableSpec


def render_create_kafka_table_ddl(
    *,
    table: DesiredKafkaTable,
    database: str,
    if_not_exists: bool = False,
) -> str:
    """Render CREATE TABLE DDL for a desired Kafka engine table."""

    spec: KafkaTableSpec = table.spec
    rendered_column_definitions: str = ",\n    ".join(
        _render_column_definition(column) for column in spec.columns
    )
    create_prefix: str = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    return (
        f"{create_prefix} {database}.{table.name} (\n"
        f"    {rendered_column_definitions}\n"
        ") ENGINE = Kafka\n"
        f"SETTINGS {_render_kafka_settings(table=table, database=database)}"
    )


def _render_column_definition(column: Column) -> str:
    """Render a single Kafka table column definition."""

    if column.default is None:
        return f"{column.name} {column.type}"
    return f"{column.name} {column.type} DEFAULT {column.default}"


def _render_kafka_settings(*, table: DesiredKafkaTable, database: str) -> str:
    """Render the Kafka engine settings clause."""

    consumer_group_name: str = _database_scoped_consumer_group(
        consumer_group=table.spec.kafka.consumer_group,
        database=database,
    )
    rendered_settings: list[str] = [
        f"kafka_broker_list = '{table.spec.kafka.broker_list}'",
        f"kafka_topic_list = '{table.spec.kafka.topic}'",
        f"kafka_group_name = '{consumer_group_name}'",
        f"kafka_format = '{table.spec.kafka.format}'",
    ]
    if table.spec.kafka.settings is not None:
        for key, value in sorted(table.spec.kafka.settings.items()):
            rendered_settings.append(f"{key} = '{value}'")
    return ", ".join(rendered_settings)


def _database_scoped_consumer_group(*, consumer_group: str, database: str | None) -> str:
    if database is None:
        return consumer_group
    normalized_database: str = database.replace("-", "_")
    return f"{consumer_group}_{normalized_database}"
