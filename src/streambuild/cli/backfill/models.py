from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import DeploymentPlan


@dataclass(frozen=True)
class BackfillCommandOptions:
    pipelines_root: Path
    database: str | None
    metadata_database: str | None
    selectors: tuple[str, ...]
    deployment_id: str | None
    full_refresh: bool
    start_time: str | None
    json_output: bool
    verbose: bool
    auto_approve: bool


@dataclass(frozen=True)
class BackfillPreviewContext:
    resolved_database: str
    resolved_metadata_database: str
    desired_state: DesiredState
    plan: DeploymentPlan
    replay_lineage_mode: ReplayLineageMode
    full_refresh_keys: frozenset[ObjectKey] = frozenset()
    start_time_keys: frozenset[ObjectKey] = frozenset()
    start_time: str | None = None
