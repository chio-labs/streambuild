"""Non-blocking cached Kafka topic inventory reads for the development UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server._helpers.broker.client import kafka_client_key
from streambuild.dev_server.classes.kafka_topic_collector import KafkaTopicCollector
from streambuild.dev_server.models import KafkaTopicsSnapshot
from streambuild.dev_server.types import KafkaClientKey

_CACHE_SECONDS: float = 600.0
_FAILURE_RETRY_SECONDS: float = 600.0
_MAX_CACHE_ENTRIES: int = 32
_MAX_WORKERS: int = 2


class KafkaTopicReader:
    """Return cached topic inventories immediately and refresh stale entries."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        collector: Callable[..., KafkaTopicsSnapshot] | None = None,
    ) -> None:
        self._clock = clock
        retained_collector: KafkaTopicCollector | None = None
        if collector is None:
            retained_collector = KafkaTopicCollector()
            collector = retained_collector
        self._collector = collector
        self._retained_collector = retained_collector
        self._lock = threading.Lock()
        self._cache: dict[KafkaClientKey, tuple[float, KafkaTopicsSnapshot | None]] = {}
        self._refreshing: set[KafkaClientKey] = set()
        self._executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="streambuild-kafka-topics",
        )

    def read(self, *, kafka: KafkaSettings) -> KafkaTopicsSnapshot | None:
        """Return the cached inventory and schedule a non-blocking refresh when stale."""

        key: KafkaClientKey = kafka_client_key(kafka=kafka)
        now: float = self._clock()
        with self._lock:
            entry: tuple[float, KafkaTopicsSnapshot | None] | None = self._cache.get(key)
            if entry is not None and now < entry[0]:
                return entry[1]
            if key not in self._refreshing:
                self._refreshing.add(key)
                self._executor.submit(self._refresh, key=key, kafka=kafka)
            return None if entry is None else entry[1]

    def close(self) -> None:
        """Finish in-flight refreshes and close retained broker connections."""

        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._retained_collector is not None:
            self._retained_collector.close()

    def _refresh(self, *, key: KafkaClientKey, kafka: KafkaSettings) -> None:
        snapshot: KafkaTopicsSnapshot | None
        succeeded: bool = True
        try:
            snapshot = self._collector(kafka=kafka)
        except Exception:
            snapshot = None
            succeeded = False
        with self._lock:
            previous: tuple[float, KafkaTopicsSnapshot | None] | None = self._cache.get(key)
            if len(self._cache) >= _MAX_CACHE_ENTRIES and key not in self._cache:
                oldest_key: KafkaClientKey = min(self._cache, key=lambda item: self._cache[item][0])
                self._cache.pop(oldest_key)
            now: float = self._clock()
            self._cache[key] = (
                now + (_CACHE_SECONDS if succeeded else _FAILURE_RETRY_SECONDS),
                snapshot if succeeded or previous is None else previous[1],
            )
            self._refreshing.discard(key)
