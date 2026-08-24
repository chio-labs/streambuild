"""Publish recorded destruction execution."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.destruction._helpers.execution import (
    execute_destruction as _execute_destruction,
)
from streambuild.executor.destruction.models import (
    DestructionExecutionResult,
    DestructionPlan,
)
from streambuild.executor.destruction.types import DestructionPlanStore


def execute_destruction(
    *,
    frozen_plan: DestructionPlan,
    actor_id: str,
    actor_name: str,
    challenge_responses: tuple[str, ...],
    reviewed_at: datetime,
    store: DestructionPlanStore,
    connection: AdapterConnection,
    observation_connection: AdapterConnection,
    project_dir: Path,
    replan: Callable[[], DestructionPlan],
) -> DestructionExecutionResult:
    """Execute a reviewed and actor-bound destruction plan exactly once."""

    return _execute_destruction(
        frozen_plan=frozen_plan,
        actor_id=actor_id,
        actor_name=actor_name,
        challenge_responses=challenge_responses,
        reviewed_at=reviewed_at,
        store=store,
        connection=connection,
        observation_connection=observation_connection,
        project_dir=project_dir,
        replan=replan,
    )
