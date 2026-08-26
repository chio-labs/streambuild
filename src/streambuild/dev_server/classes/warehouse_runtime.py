"""Recoverable warehouse connections owned by the dev-server lifecycle."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import monotonic

from streambuild.adapter.classes.adapter_connection import AdapterConnection

_INITIAL_RETRY_SECONDS: float = 1.0
_MAX_RETRY_SECONDS: float = 30.0
_HEALTH_CHECK_SECONDS: float = 10.0
_READ_CONNECTION_LIMIT: int = 4


class WarehouseRuntime:
    """Hold primary and observation connections, reconnecting without stopping the UI."""

    def __init__(
        self,
        *,
        connection: AdapterConnection | None,
        observation_connection: AdapterConnection | None,
        connection_factory: Callable[[], AdapterConnection] | None,
        observation_connection_factory: Callable[[], AdapterConnection] | None,
        database: str | None,
        query_lock: threading.Lock | threading.RLock | None = None,
    ) -> None:
        self._connection = connection
        self._observation_connection = observation_connection
        self._connection_factory = connection_factory
        self._observation_connection_factory = observation_connection_factory
        self._owns_connection = False
        self._owns_observation_connection = False
        self._database = database
        self._query_lock = query_lock or threading.RLock()
        self._primary_healthy = connection is not None
        self._observation_healthy = observation_connection is not None
        self._lock = threading.RLock()
        self._attempt_lock = threading.Lock()
        self._read_semaphore = threading.BoundedSemaphore(_READ_CONNECTION_LIMIT)
        self._stop = threading.Event()
        self._retry_now = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None
        self._last_attempt_at: str | None = None
        self._next_attempt_at: str | None = None
        self._retry_seconds = _INITIAL_RETRY_SECONDS

    @property
    def connection(self) -> AdapterConnection | None:
        """Return the current primary connection, if available."""

        with self._lock:
            return self._connection if self._primary_healthy else None

    @property
    def observation_connection(self) -> AdapterConnection | None:
        """Return the current observation connection, if available."""

        with self._lock:
            return self._observation_connection if self._observation_healthy else None

    def start(self) -> None:
        """Start background recovery once; an existing connection remains authoritative."""

        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="streambuild-warehouse", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop recovery and close every runtime-owned connection."""

        self._stop.set()
        self._retry_now.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            connections: tuple[
                tuple[AdapterConnection | None, bool],
                tuple[AdapterConnection | None, bool],
            ] = (
                (self._observation_connection, self._owns_observation_connection),
                (self._connection, self._owns_connection),
            )
            self._observation_connection = None
            self._connection = None
        for connection, owned in connections:
            if connection is not None and owned:
                connection.close()

    def connect_now(self) -> bool:
        """Attempt missing connections immediately, returning primary availability."""

        with self._attempt_lock:
            if self._raw_connection() is not None:
                self._probe_connection()
            else:
                self._attempt_connections()
        return self.connection is not None

    def request_health_check(self) -> None:
        """Wake the recovery worker without blocking the caller on warehouse traffic."""

        self._retry_now.set()

    def status(self) -> dict[str, object]:
        """Return cheap connection and recovery state for the status endpoint."""

        with self._lock:
            connected: bool = self._connection is not None and self._primary_healthy
            observation_degraded: bool = (
                connected
                and self._observation_connection_factory is not None
                and (self._observation_connection is None or not self._observation_healthy)
            )
            return {
                "connected": connected,
                "state": (
                    "degraded"
                    if observation_degraded
                    else "connected"
                    if connected
                    else "retrying"
                    if self._connection_factory is not None
                    else "unavailable"
                ),
                "database": self._database,
                "error": self._last_error,
                "lastAttemptAt": self._last_attempt_at,
                "nextAttemptAt": self._next_attempt_at,
            }

    @contextmanager
    def read_connection(self) -> Iterator[AdapterConnection | None]:
        """Yield an isolated bounded read connection, falling back to the shared client."""

        factory: Callable[[], AdapterConnection] | None = (
            self._observation_connection_factory or self._connection_factory
        )
        if factory is None:
            with self._query_lock:
                yield self.observation_connection or self.connection
            return
        self._read_semaphore.acquire()
        connection: AdapterConnection | None = None
        try:
            connection = factory()
            yield connection
        finally:
            if connection is not None:
                connection.close()
            self._read_semaphore.release()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._connections_missing():
                with self._attempt_lock:
                    self._attempt_connections()
            if not self._connections_missing():
                with self._attempt_lock:
                    self._probe_connection()
                self._retry_now.wait(timeout=_HEALTH_CHECK_SECONDS)
                self._retry_now.clear()
                continue
            delay: float
            with self._lock:
                delay = self._retry_seconds
                self._next_attempt_at = (datetime.now(tz=UTC) + timedelta(seconds=delay)).isoformat(
                    timespec="seconds"
                )
            started: float = monotonic()
            self._retry_now.wait(timeout=delay)
            self._retry_now.clear()
            if monotonic() - started >= delay:
                with self._lock:
                    self._retry_seconds = min(delay * 2, _MAX_RETRY_SECONDS)

    def _connections_missing(self) -> bool:
        return (self._raw_connection() is None and self._connection_factory is not None) or (
            self._raw_observation_connection() is None
            and self._observation_connection_factory is not None
        )

    def _raw_connection(self) -> AdapterConnection | None:
        with self._lock:
            return self._connection

    def _raw_observation_connection(self) -> AdapterConnection | None:
        with self._lock:
            return self._observation_connection

    def _probe_connection(self) -> None:
        connection: AdapterConnection | None = self._raw_connection()
        if connection is None:
            return
        try:
            with self._query_lock:
                _ = connection.capture_warehouse_timestamp()
        except Exception as error:
            with self._lock:
                self._primary_healthy = False
                self._last_error = str(error)
                self._last_attempt_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
                self._next_attempt_at = (
                    datetime.now(tz=UTC) + timedelta(seconds=_HEALTH_CHECK_SECONDS)
                ).isoformat(timespec="seconds")
            return
        with self._lock:
            self._primary_healthy = True
            self._last_error = None
            self._last_attempt_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
            self._next_attempt_at = None
        observation_connection: AdapterConnection | None = self._raw_observation_connection()
        if observation_connection is None:
            return
        try:
            with self._query_lock:
                _ = observation_connection.capture_warehouse_timestamp()
        except Exception as error:
            with self._lock:
                self._observation_healthy = False
                self._last_error = f"observation connection: {error}"
            return
        with self._lock:
            self._observation_healthy = True
            self._last_error = None

    def _attempt_connections(self) -> None:
        with self._lock:
            self._last_attempt_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
            self._next_attempt_at = None
        if self.connection is None and self._connection_factory is not None:
            connection: AdapterConnection | None = None
            try:
                connection = self._connection_factory()
                if self._database is not None:
                    connection.validate_metadata_state(self._database)
            except Exception as error:
                if connection is not None:
                    connection.close()
                with self._lock:
                    self._last_error = str(error)
                return
            with self._lock:
                self._connection = connection
                self._owns_connection = True
                self._primary_healthy = True
                self._last_error = None
                self._retry_seconds = _INITIAL_RETRY_SECONDS
        if self.observation_connection is None and self._observation_connection_factory is not None:
            try:
                observation_connection: AdapterConnection = self._observation_connection_factory()
            except Exception as error:
                with self._lock:
                    self._last_error = f"observation connection: {error}"
                return
            with self._lock:
                self._observation_connection = observation_connection
                self._owns_observation_connection = True
                self._observation_healthy = True
                self._last_error = None
                self._retry_seconds = _INITIAL_RETRY_SECONDS
