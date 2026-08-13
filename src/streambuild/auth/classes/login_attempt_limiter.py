"""Bound expensive password verification attempts in one server process."""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import HTTPException

from streambuild.auth.constants import (
    LOGIN_ATTEMPT_WINDOW_MINUTES,
    LOGIN_IP_ATTEMPT_LIMIT,
    LOGIN_LIMITER_MAX_KEYS,
    LOGIN_USER_ATTEMPT_LIMIT,
)


class LoginAttemptLimiter:
    """Apply bounded per-user and per-client login throttling."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, *, ip_key: str, user_key: str) -> None:
        with self._lock:
            self._prune()
            if len(self._attempts) >= LOGIN_LIMITER_MAX_KEYS and user_key not in self._attempts:
                self._raise_limit()
            if (
                len(self._active_attempts(key=user_key)) >= LOGIN_USER_ATTEMPT_LIMIT
                or len(self._active_attempts(key=ip_key)) >= LOGIN_IP_ATTEMPT_LIMIT
            ):
                self._raise_limit()

    def failed(self, *, ip_key: str, user_key: str) -> None:
        with self._lock:
            now: datetime = datetime.now(UTC)
            self._active_attempts(key=ip_key).append(now)
            self._active_attempts(key=user_key).append(now)

    def succeeded(self, *, ip_key: str, user_key: str) -> None:
        with self._lock:
            self._attempts.pop(ip_key, None)
            self._attempts.pop(user_key, None)

    def _active_attempts(self, *, key: str) -> deque[datetime]:
        attempts: deque[datetime] = self._attempts[key]
        cutoff: datetime = datetime.now(UTC) - timedelta(minutes=LOGIN_ATTEMPT_WINDOW_MINUTES)
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts

    def _prune(self) -> None:
        for key in tuple(self._attempts):
            if not self._active_attempts(key=key):
                self._attempts.pop(key, None)

    @staticmethod
    def _raise_limit() -> None:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts; try again later",
        )
