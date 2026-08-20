"""Background-refreshed warehouse overlay shared by every state request."""

from __future__ import annotations

import threading
from collections.abc import Callable

from streambuild.adapter.exceptions import AdapterError
from streambuild.dev_server.exceptions import ProjectNotCompiledError

_REFRESH_SECONDS: float = 15.0


class StateSnapshot:
    """Hold one warehouse overlay so requests never wait on per-relation reads."""

    def __init__(
        self,
        *,
        build: Callable[[], dict[str, object]],
        refresh_seconds: float = _REFRESH_SECONDS,
    ) -> None:
        self._build = build
        self._refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._payload: dict[str, object] | None = None
        self._stop = threading.Event()
        self._refresh_now = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start background refreshes once; the first request may still build inline."""

        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="streambuild-state-snapshot", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        """Stop refreshing and wait for the worker to finish."""

        self._stop.set()
        self._refresh_now.set()
        if self._thread is not None:
            self._thread.join()

    def current(self) -> dict[str, object]:
        """Return the held overlay, building it inline only before the first success."""

        with self._lock:
            held: dict[str, object] | None = self._payload
        if held is not None:
            return held
        with self._build_lock:
            with self._lock:
                held = self._payload
            if held is not None:
                return held
            return self._store(self._build())

    def refresh(self) -> dict[str, object]:
        """Rebuild now, replacing the held overlay."""

        with self._build_lock:
            return self._store(self._build())

    def invalidate(self) -> None:
        """Drop the held overlay so the next request rebuilds against new definitions."""

        with self._lock:
            self._payload = None

    def _store(self, payload: dict[str, object]) -> dict[str, object]:
        with self._lock:
            self._payload = payload
        return payload

    def _run(self) -> None:
        while not self._stop.is_set():
            self._refresh_now.wait(timeout=self._refresh_seconds)
            self._refresh_now.clear()
            if self._stop.is_set():
                return
            try:
                _ = self.refresh()
            except (AdapterError, ProjectNotCompiledError):
                continue
