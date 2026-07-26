"""Render CREATE TABLE DDL for Kafka engine tables."""

from streambuild.clickhouse.render._helpers.column_definitions import render_column_definition
from streambuild.clickhouse.render._helpers.kafka_settings import render_kafka_settings
from streambuild.compiler.shared.models import DesiredKafkaTable, KafkaTableSpec


def render_create_kafka_table_ddl(
    *,
    table: DesiredKafkaTable,
    database: str,
    if_not_exists: bool = False,
) -> str:
    """Render CREATE TABLE DDL for a desired Kafka engine table."""

    spec: KafkaTableSpec = table.spec
    rendered_column_definitions: str = ",\n    ".join(
        render_column_definition(column) for column in spec.columns
    )
    create_prefix: str = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE TABLE"
    return (
        f"{create_prefix} {database}.{table.name} (\n"
        f"    {rendered_column_definitions}\n"
        ") ENGINE = Kafka\n"
        f"SETTINGS {render_kafka_settings(table=table, database=database)}"
    )
