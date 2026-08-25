"""Publish recorded destruction execution."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.destruction._helpers.execution import (
    execute_destruction as _execute_destruction,
)
from streambuild.executor.destruction.models import (
    DestructionActor,
    DestructionExecutionResult,
    DestructionPlan,
)
from streambuild.executor.destruction.types import DestructionPlanStore


def execute_destruction(
    *,
    frozen_plan: DestructionPlan,
    actor: DestructionActor,
    challenge_responses: tuple[str, ...],
    reviewed_at: datetime,
    store: DestructionPlanStore,
    connection: AdapterConnection,
    observation_connection: AdapterConnection,
    project_dir: Path,
    replan: Callable[[], DestructionPlan],
    invocation_id: str | None = None,
) -> DestructionExecutionResult:
    """Execute a reviewed and actor-bound destruction plan exactly once."""

    return _execute_destruction(
        frozen_plan=frozen_plan,
        actor=actor,
        challenge_responses=challenge_responses,
        reviewed_at=reviewed_at,
        store=store,
        connection=connection,
        observation_connection=observation_connection,
        project_dir=project_dir,
        replan=replan,
        invocation_id=invocation_id,
    )
