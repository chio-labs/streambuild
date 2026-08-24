"""Publish read-only destruction planning."""

from datetime import datetime, timedelta

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.destruction._helpers.planning import (
    plan_destruction as _plan_destruction,
)
from streambuild.executor.destruction.constants import DEFAULT_DESTRUCTION_PLAN_TTL
from streambuild.executor.destruction.models import DestructionPlan, DestructionRequest
from streambuild.executor.destruction.types import DestructionPlanningConnection


def plan_destruction(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_DESTRUCTION_PLAN_TTL,
    plan_id: str | None = None,
) -> DestructionPlan:
    """Build a frozen impact plan using only read-only adapter interactions."""

    return _plan_destruction(
        request=request,
        analysis=analysis,
        connection=connection,
        now=now,
        ttl=ttl,
        plan_id=plan_id,
    )
