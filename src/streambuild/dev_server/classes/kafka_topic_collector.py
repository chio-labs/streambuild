"""Retained Kafka clients for topic inventory reads."""

import logging
import threading
from collections.abc import Callable

from kafka import KafkaAdminClient

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server._helpers.broker.client import (
    build_kafka_client_config,
    kafka_client_key,
)
from streambuild.dev_server._helpers.broker.snapshots import build_kafka_topics_snapshot
from streambuild.dev_server.exceptions import KafkaCollectorClosedError
from streambuild.dev_server.models import KafkaTopicsSnapshot
from streambuild.dev_server.types import KafkaClientKey

logger: logging.Logger = logging.getLogger(__name__)


class KafkaTopicCollector:
    """Collect topic inventories through retained clients shared by broker configuration."""

    def __init__(
        self,
        *,
        admin_factory: Callable[..., KafkaAdminClient] = KafkaAdminClient,
    ) -> None:
        self._admin_factory = admin_factory
        self._lock = threading.Lock()
        self._admins: dict[KafkaClientKey, KafkaAdminClient] = {}
        self._client_locks: dict[KafkaClientKey, threading.Lock] = {}
        self._reads: dict[KafkaClientKey, int] = {}
        self._opened_clients = 0
        self._closed_clients = 0
        self._closed = False

    def __call__(self, *, kafka: KafkaSettings) -> KafkaTopicsSnapshot:
        """Read the topic inventory while keeping its broker connection open."""

        key, admin, client_lock = self._acquire_client(kafka=kafka)
        try:
            snapshot: KafkaTopicsSnapshot = build_kafka_topics_snapshot(
                metadata=admin.describe_topics()
            )
            self._reads[key] += 1
            logger.warning(
                "Kafka topic client %s brokers=%s reads=%d opened=%d closed=%d active=%d",
                "opened" if self._reads[key] == 1 else "reused",
                kafka.broker_list,
                self._reads[key],
                self._opened_clients,
                self._closed_clients,
                self._opened_clients - self._closed_clients,
            )
            return snapshot
        finally:
            client_lock.release()

    def close(self) -> None:
        """Close all retained broker connections."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            keys: tuple[KafkaClientKey, ...] = tuple(self._admins)
        for key in keys:
            with self._client_locks[key]:
                try:
                    self._admins[key].close()
                finally:
                    self._closed_clients += 1
                    logger.warning(
                        "Kafka topic client closed reads=%d opened=%d closed=%d active=%d",
                        self._reads[key],
                        self._opened_clients,
                        self._closed_clients,
                        self._opened_clients - self._closed_clients,
                    )

    def _acquire_client(
        self, *, kafka: KafkaSettings
    ) -> tuple[KafkaClientKey, KafkaAdminClient, threading.Lock]:
        key: KafkaClientKey = kafka_client_key(kafka=kafka)
        with self._lock:
            if self._closed:
                raise KafkaCollectorClosedError("Kafka topic collector is closed")
            if key not in self._admins:
                self._admins[key] = self._admin_factory(**build_kafka_client_config(kafka=kafka))
                self._client_locks[key] = threading.Lock()
                self._reads[key] = 0
                self._opened_clients += 1
            client_lock: threading.Lock = self._client_locks[key]
            client_lock.acquire()
            return key, self._admins[key], client_lock
