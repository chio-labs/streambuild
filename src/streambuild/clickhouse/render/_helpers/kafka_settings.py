"""Render the SETTINGS clause for Kafka engine tables."""

from streambuild.compiler.shared.models import DesiredKafkaTable


def render_kafka_settings(*, table: DesiredKafkaTable, database: str) -> str:
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
    """Scope a consumer group to its database so parallel targets do not share offsets."""

    if database is None:
        return consumer_group
    normalized_database: str = database.replace("-", "_")
    return f"{consumer_group}_{normalized_database}"
