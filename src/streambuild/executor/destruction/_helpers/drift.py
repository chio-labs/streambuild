"""Fresh-plan drift verification."""

from collections.abc import Callable

from streambuild.executor.destruction.exceptions import (
    DestructionDriftError,
    DestructionError,
)
from streambuild.executor.destruction.models import DestructionPlan


def verify_destruction_drift(
    *, frozen_plan: DestructionPlan, replan: Callable[[], DestructionPlan]
) -> DestructionPlan:
    """Replan immediately and reject manifest or warehouse impact drift."""

    try:
        current_plan: DestructionPlan = replan()
    except DestructionDriftError:
        raise
    except DestructionError as error:
        raise DestructionDriftError(
            f"Current destruction impact can no longer be planned: {error}"
        ) from error
    if current_plan.manifest_fingerprint != frozen_plan.manifest_fingerprint:
        raise DestructionDriftError("Current manifest differs from the reviewed destruction plan")
    if current_plan.plan_fingerprint != frozen_plan.plan_fingerprint:
        raise DestructionDriftError("Current destruction impact differs from the reviewed plan")
    return current_plan
