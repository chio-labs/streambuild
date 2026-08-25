"""Typed Kafka retention rendering boundary."""

from streambuild.compiler.compile._helpers.retention import (
    render_kafka_retention as _render_kafka_retention,
)
from streambuild.compiler.discovery.models import KafkaRetentionPolicy


def render_kafka_retention(*, policy: KafkaRetentionPolicy) -> str:
    """Render one managed Kafka retention policy."""

    return _render_kafka_retention(policy=policy)
