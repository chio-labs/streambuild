"""Publish deterministic destruction challenge construction."""

from streambuild.executor.destruction._helpers.planning import (
    build_destruction_challenges as _build_destruction_challenges,
)


def build_destruction_challenges(
    *, pipeline_names: tuple[str, ...], production_reset: bool = False
) -> tuple[str, ...]:
    """Return stable, ordered challenge values for the affected pipeline set."""

    return _build_destruction_challenges(
        pipeline_names=pipeline_names,
        production_reset=production_reset,
    )
