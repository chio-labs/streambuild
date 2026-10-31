"""Relax cyclic collection while one compile invocation retains parsed trees."""

from __future__ import annotations

import gc
from collections.abc import Iterator
from contextlib import contextmanager

_RELAXED_THRESHOLDS: tuple[int, int, int] = (2000, 100, 100)


@contextmanager
def deferred_cycle_collection() -> Iterator[None]:
    """Defer generational collection, since retained parse trees hold no cycles."""

    previous_thresholds: tuple[int, ...] = gc.get_threshold()
    gc.set_threshold(
        *(
            max(previous, relaxed)
            for previous, relaxed in zip(previous_thresholds, _RELAXED_THRESHOLDS, strict=True)
        )
    )
    try:
        yield
    finally:
        gc.set_threshold(*previous_thresholds)
