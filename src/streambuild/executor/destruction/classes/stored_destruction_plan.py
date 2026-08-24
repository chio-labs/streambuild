"""Mutable storage state for one frozen destruction plan."""

from datetime import datetime

from streambuild.executor.destruction.models import DestructionPlan


class StoredDestructionPlan:
    """Actor and review state attached to one frozen plan."""

    def __init__(self, *, plan: DestructionPlan, actor: str) -> None:
        self.plan: DestructionPlan = plan
        self.actor: str = actor
        self.reviewed_at: datetime | None = None
