"""Publish fresh-plan drift verification."""

from collections.abc import Callable

from sqltide.executor.destruction._helpers.drift import (
    verify_destruction_drift as _verify_destruction_drift,
)
from sqltide.executor.destruction.models import DestructionPlan


def verify_destruction_drift(
    *, frozen_plan: DestructionPlan, replan: Callable[[], DestructionPlan]
) -> DestructionPlan:
    """Replan immediately and reject manifest or warehouse impact drift."""

    return _verify_destruction_drift(frozen_plan=frozen_plan, replan=replan)
