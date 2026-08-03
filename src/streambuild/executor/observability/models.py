"""Inputs used to construct terminal invocation observations."""

from dataclasses import dataclass
from pathlib import Path


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
