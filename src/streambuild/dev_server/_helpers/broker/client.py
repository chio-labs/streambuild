"""Shared Kafka client identity and configuration helpers."""

from collections.abc import Mapping

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server.constants import (
    KAFKA_REQUEST_TIMEOUT_MS,
    KAFKA_SECURITY_PROTOCOL_CONFIG_NAME,
)
from streambuild.dev_server.types import KafkaClientKey


def build_kafka_client_config(*, kafka: KafkaSettings) -> dict[str, object]:
    """Translate resolved managed-source Kafka settings into kafka-python config."""

    settings: Mapping[str, str] = kafka.settings or {}
    config: dict[str, object] = {
        "bootstrap_servers": [item.strip() for item in kafka.broker_list.split(",")],
        "request_timeout_ms": KAFKA_REQUEST_TIMEOUT_MS,
        "api_version_auto_timeout_ms": KAFKA_REQUEST_TIMEOUT_MS,
    }
    translated_settings: tuple[tuple[str, str], ...] = (
        ("kafka_security_protocol", "security_protocol"),
        ("kafka_sasl_mechanism", "sasl_mechanism"),
        ("kafka_sasl_username", "sasl_plain_username"),
        ("kafka_sasl_password", "sasl_plain_password"),
    )
    source_name: str
    target_name: str
    for source_name, target_name in translated_settings:
        value: str | None = settings.get(source_name)
        if value is not None:
            config[target_name] = (
                value.upper() if target_name == KAFKA_SECURITY_PROTOCOL_CONFIG_NAME else value
            )
    return config


def kafka_client_key(*, kafka: KafkaSettings) -> KafkaClientKey:
    """Identify sources that can safely share authenticated Kafka clients."""

    return kafka.broker_list, tuple(sorted((kafka.settings or {}).items()))
