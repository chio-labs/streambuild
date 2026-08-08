"""Resolve the effective ClickHouse Kafka consumer group."""


def database_scoped_consumer_group(*, consumer_group: str, database: str) -> str:
    """Return the consumer group ClickHouse uses for one target database."""

    normalized_database: str = database.replace("-", "_")
    return f"{consumer_group}_{normalized_database}"
