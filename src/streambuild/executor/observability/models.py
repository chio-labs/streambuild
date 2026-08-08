"""Inputs used to construct terminal invocation observations."""

from dataclasses import dataclass
from pathlib import Path

from streambuild.executor.observability.types import QualityResultTrigger


@dataclass(frozen=True)
class TerminalInvocation:
    """Command outcome fields captured at one finite CLI boundary."""

    project_dir: Path
    target_identity: str
    command: str
    mode: str | None
    outcome: str
    exit_code: int
    materialized_outcome: str | None
    deployment_id: str | None
    workflow_id: str | None
    selected_node_count: int
    error_message: str | None
    summary: dict[str, object]


@dataclass(frozen=True)
class QualityResultContext:
    """Trigger, logical slot, and policy snapshot for one quality attempt."""

    trigger: QualityResultTrigger | str
    scheduled_for: str | None = None
    cadence_seconds: int | None = None
    warmup_seconds: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "trigger", QualityResultTrigger(self.trigger))
