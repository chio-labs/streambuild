"""Non-blocking cached Kafka consumer-group lag reads for the development UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server._helpers.broker.client import kafka_client_key
from streambuild.dev_server.classes.kafka_lag_collector import KafkaLagCollector
from streambuild.dev_server.models import KafkaLagSnapshot

_CACHE_SECONDS: float = 60.0
_FAILURE_RETRY_SECONDS: float = 10.0
_MAX_CACHE_ENTRIES: int = 128
_MAX_PENDING_REFRESHES: int = 32
_MAX_WORKERS: int = 4


class KafkaLagReader:
    """Return cached lag immediately and refresh stale values on a daemon thread."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        collector: Callable[..., KafkaLagSnapshot] | None = None,
    ) -> None:
        self._clock = clock
        retained_collector: KafkaLagCollector | None = None
        if collector is None:
            retained_collector = KafkaLagCollector()
            collector = retained_collector
        self._collector = collector
        self._retained_collector = retained_collector
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
            kafka_client_key(kafka=kafka),
            kafka.topic,
            kafka.consumer_group,
            database,
        )
        now: float = self._clock()
        with self._lock:
            entry: tuple[float, KafkaLagSnapshot | None] | None = self._cache.get(key)
            if entry is not None and now < entry[0]:
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
        """Finish in-flight refreshes and close retained broker connections."""

        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._retained_collector is not None:
            self._retained_collector.close()

    def _refresh(self, *, key: tuple[object, ...], kafka: KafkaSettings, database: str) -> None:
        snapshot: KafkaLagSnapshot | None
        succeeded: bool = True
        try:
            snapshot = self._collector(kafka=kafka, database=database)
        except Exception:
            snapshot = None
            succeeded = False
        with self._lock:
            previous: tuple[float, KafkaLagSnapshot | None] | None = self._cache.get(key)
            if len(self._cache) >= _MAX_CACHE_ENTRIES and key not in self._cache:
                oldest_key: tuple[object, ...] = min(
                    self._cache, key=lambda item: self._cache[item][0]
                )
                self._cache.pop(oldest_key)
            now: float = self._clock()
            self._cache[key] = (
                now + (_CACHE_SECONDS if succeeded else _FAILURE_RETRY_SECONDS),
                snapshot if succeeded or previous is None else previous[1],
            )
            self._refreshing.discard(key)
