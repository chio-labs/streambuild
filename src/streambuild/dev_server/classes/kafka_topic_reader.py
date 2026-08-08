"""Non-blocking cached Kafka topic inventory reads for the development UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from kafka import KafkaAdminClient

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server.classes.kafka_lag_reader import build_kafka_client_config
from streambuild.dev_server.models import KafkaTopicInfo, KafkaTopicsSnapshot

_CACHE_SECONDS: float = 10.0
_MAX_CACHE_ENTRIES: int = 32
_MAX_WORKERS: int = 2


def build_kafka_topics_snapshot(*, metadata: Sequence[Mapping[str, object]]) -> KafkaTopicsSnapshot:
    """Map raw kafka-python describe_topics metadata into the topic inventory."""

    topics: list[KafkaTopicInfo] = []
    for entry in metadata:
        partitions: object = entry.get("partitions", ())
        partition_list: tuple[Mapping[str, object], ...] = tuple(
            cast("Mapping[str, object]", partition)
            for partition in (partitions if isinstance(partitions, list | tuple) else ())
            if isinstance(partition, Mapping)
        )
        replication_factor: int = 0
        for partition in partition_list:
            replicas: object = partition.get("replicas")
            if isinstance(replicas, list | tuple):
                replication_factor = max(replication_factor, len(replicas))
        topics.append(
            KafkaTopicInfo(
                name=str(entry.get("topic", "")),
                partition_count=len(partition_list),
                replication_factor=replication_factor,
                internal=bool(entry.get("is_internal", False)),
            )
        )
    return KafkaTopicsSnapshot(topics=tuple(sorted(topics, key=lambda topic: topic.name)))


def collect_kafka_topics(*, kafka: KafkaSettings) -> KafkaTopicsSnapshot:
    """Read the full topic inventory from one broker list without consuming."""

    admin: KafkaAdminClient = KafkaAdminClient(**build_kafka_client_config(kafka=kafka))
    try:
        return build_kafka_topics_snapshot(metadata=admin.describe_topics())
    finally:
        admin.close()


class KafkaTopicReader:
    """Return cached topic inventories immediately and refresh stale entries."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        collector: Callable[..., KafkaTopicsSnapshot] = collect_kafka_topics,
    ) -> None:
        self._clock = clock
        self._collector = collector
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, KafkaTopicsSnapshot | None]] = {}
        self._refreshing: set[str] = set()
        self._executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="streambuild-kafka-topics",
        )

    def read(self, *, kafka: KafkaSettings) -> KafkaTopicsSnapshot | None:
        """Return the cached inventory and schedule a non-blocking refresh when stale."""

        key: str = kafka.broker_list
        now: float = self._clock()
        with self._lock:
            entry: tuple[float, KafkaTopicsSnapshot | None] | None = self._cache.get(key)
            if entry is not None and now - entry[0] < _CACHE_SECONDS:
                return entry[1]
            if key not in self._refreshing:
                self._refreshing.add(key)
                self._executor.submit(self._refresh, key=key, kafka=kafka)
            return None if entry is None else entry[1]

    def close(self) -> None:
        """Stop queued refreshes without waiting for in-flight broker requests."""

        self._executor.shutdown(wait=False, cancel_futures=True)

    def _refresh(self, *, key: str, kafka: KafkaSettings) -> None:
        snapshot: KafkaTopicsSnapshot | None
        try:
            snapshot = self._collector(kafka=kafka)
        except Exception:
            snapshot = None
        with self._lock:
            if len(self._cache) >= _MAX_CACHE_ENTRIES and key not in self._cache:
                oldest_key: str = min(self._cache, key=lambda item: self._cache[item][0])
                self._cache.pop(oldest_key)
            self._cache[key] = (self._clock(), snapshot)
            self._refreshing.discard(key)
