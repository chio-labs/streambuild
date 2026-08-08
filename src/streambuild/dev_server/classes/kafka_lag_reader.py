"""Non-blocking cached Kafka consumer-group lag reads for the development UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor

from kafka import KafkaAdminClient, KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata

from streambuild.adapters.clickhouse.main.database_scoped_consumer_group import (
    database_scoped_consumer_group,
)
from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server.constants import KAFKA_SECURITY_PROTOCOL_CONFIG_NAME
from streambuild.dev_server.models import KafkaLagSnapshot, KafkaPartitionLag

_CACHE_SECONDS: float = 10.0
_REQUEST_TIMEOUT_MS: int = 5_000
_MAX_CACHE_ENTRIES: int = 128
_MAX_PENDING_REFRESHES: int = 32
_MAX_WORKERS: int = 4


def build_kafka_lag_snapshot(
    *,
    partition_ids: frozenset[int],
    committed_offsets: Mapping[int, int],
    end_offsets: Mapping[int, int],
) -> KafkaLagSnapshot:
    """Build exact lag, leaving totals unknown when a non-empty partition has no commit."""

    partitions: list[KafkaPartitionLag] = []
    total_messages: int = 0
    complete: bool = True
    if not partition_ids:
        return KafkaLagSnapshot(total_messages=None, partitions=())
    for partition in sorted(partition_ids):
        end_offset: int = end_offsets[partition]
        committed_offset: int | None = committed_offsets.get(partition)
        lag_messages: int | None
        if committed_offset is None and end_offset == 0:
            lag_messages = 0
        elif committed_offset is None:
            lag_messages = None
            complete = False
        else:
            lag_messages = max(0, end_offset - committed_offset)
        if lag_messages is not None:
            total_messages += lag_messages
        partitions.append(
            KafkaPartitionLag(
                partition=partition,
                committed_offset=committed_offset,
                end_offset=end_offset,
                lag_messages=lag_messages,
            )
        )
    return KafkaLagSnapshot(
        total_messages=total_messages if complete else None,
        partitions=tuple(partitions),
    )


def collect_kafka_lag(
    *,
    kafka: KafkaSettings,
    database: str,
) -> KafkaLagSnapshot:
    """Read committed and broker-end offsets without joining or consuming from the group."""

    if kafka.consumer_group is None:
        return KafkaLagSnapshot(total_messages=None, partitions=())
    client_config: dict[str, object] = _client_config(kafka=kafka)
    consumer_group: str = database_scoped_consumer_group(
        consumer_group=kafka.consumer_group,
        database=database,
    )
    admin: KafkaAdminClient = KafkaAdminClient(**client_config)
    try:
        consumer: KafkaConsumer = KafkaConsumer(enable_auto_commit=False, **client_config)
        try:
            raw_committed: Mapping[TopicPartition, OffsetAndMetadata] = (
                admin.list_consumer_group_offsets(consumer_group)
            )
            discovered_partitions: set[int] | None = consumer.partitions_for_topic(kafka.topic)
            topic_partitions: frozenset[int] = frozenset(discovered_partitions or ())
            partition_objects: tuple[TopicPartition, ...] = tuple(
                TopicPartition(kafka.topic, partition) for partition in sorted(topic_partitions)
            )
            raw_ends: Mapping[TopicPartition, int] = consumer.end_offsets(partition_objects)
            committed_offsets: dict[int, int] = {
                topic_partition.partition: int(metadata.offset)
                for topic_partition, metadata in raw_committed.items()
                if topic_partition.topic == kafka.topic
                and metadata.offset is not None
                and int(metadata.offset) >= 0
            }
            end_offsets: dict[int, int] = {
                topic_partition.partition: int(offset)
                for topic_partition, offset in raw_ends.items()
            }
            return build_kafka_lag_snapshot(
                partition_ids=topic_partitions,
                committed_offsets=committed_offsets,
                end_offsets=end_offsets,
            )
        finally:
            consumer.close()
    finally:
        admin.close()


class KafkaLagReader:
    """Return cached lag immediately and refresh stale values on a daemon thread."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        collector: Callable[..., KafkaLagSnapshot] = collect_kafka_lag,
    ) -> None:
        self._clock = clock
        self._collector = collector
        self._lock = threading.Lock()
        self._cache: dict[tuple[object, ...], tuple[float, KafkaLagSnapshot | None]] = {}
        self._refreshing: set[tuple[object, ...]] = set()
        self._executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="streambuild-kafka-lag",
        )

    def read(self, *, kafka: KafkaSettings, database: str) -> KafkaLagSnapshot | None:
        """Return current cached lag and schedule a non-blocking refresh when needed."""

        key: tuple[object, ...] = (
            kafka.broker_list,
            kafka.topic,
            kafka.consumer_group,
            database,
        )
        now: float = self._clock()
        with self._lock:
            entry: tuple[float, KafkaLagSnapshot | None] | None = self._cache.get(key)
            if entry is not None and now - entry[0] < _CACHE_SECONDS:
                return entry[1]
            if key not in self._refreshing and len(self._refreshing) < _MAX_PENDING_REFRESHES:
                self._refreshing.add(key)
                self._executor.submit(
                    self._refresh,
                    key=key,
                    kafka=kafka,
                    database=database,
                )
            return None if entry is None else entry[1]

    def close(self) -> None:
        """Stop queued refreshes without waiting for in-flight broker requests."""

        self._executor.shutdown(wait=False, cancel_futures=True)

    def _refresh(self, *, key: tuple[object, ...], kafka: KafkaSettings, database: str) -> None:
        snapshot: KafkaLagSnapshot | None
        try:
            snapshot = self._collector(kafka=kafka, database=database)
        except Exception:
            snapshot = None
        with self._lock:
            if len(self._cache) >= _MAX_CACHE_ENTRIES and key not in self._cache:
                oldest_key: tuple[object, ...] = min(
                    self._cache, key=lambda item: self._cache[item][0]
                )
                self._cache.pop(oldest_key)
            self._cache[key] = (self._clock(), snapshot)
            self._refreshing.discard(key)


def _client_config(*, kafka: KafkaSettings) -> dict[str, object]:
    settings: Mapping[str, str] = kafka.settings or {}
    config: dict[str, object] = {
        "bootstrap_servers": [item.strip() for item in kafka.broker_list.split(",")],
        "request_timeout_ms": _REQUEST_TIMEOUT_MS,
        "api_version_auto_timeout_ms": _REQUEST_TIMEOUT_MS,
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
