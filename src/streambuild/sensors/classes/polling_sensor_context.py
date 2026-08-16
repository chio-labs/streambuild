"""The context handed to authored polling sensor handlers."""

from __future__ import annotations


class PollingSensorContext:
    """One polling tick: last persisted cursor and success time."""

    def __init__(
        self,
        *,
        cursor: str | None = None,
        last_success_at: str | None = None,
        target: str = "",
    ) -> None:
        self._cursor: str | None = cursor
        self._last_success_at: str | None = last_success_at
        self._target: str = target

    @property
    def cursor(self) -> str | None:
        return self._cursor

    @property
    def last_success_at(self) -> str | None:
        return self._last_success_at

    @property
    def target(self) -> str:
        return self._target
