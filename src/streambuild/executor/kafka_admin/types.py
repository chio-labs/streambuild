"""Kafka admin boundary types."""

from typing import Protocol


class KafkaAdminClientProtocol(Protocol):
    """Kafka admin operations needed by committed-offset reset."""

    def delete_consumer_groups(self, group_ids: list[str]) -> list[tuple[str, object]]: ...

    def close(self) -> None: ...


class KafkaAdminClientFactory(Protocol):
    """Construct a Kafka admin client from kafka-python keyword configuration."""

    def __call__(self, **config: object) -> KafkaAdminClientProtocol: ...
