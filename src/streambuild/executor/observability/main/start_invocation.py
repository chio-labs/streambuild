"""Capture invocation start evidence."""

from datetime import UTC, datetime
from time import monotonic_ns
from uuid import uuid4


def start_invocation() -> tuple[str, str, int]:
    """Capture one process-local invocation identity, wall time, and monotonic start."""

    started_at: str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(uuid4()), started_at, monotonic_ns()
