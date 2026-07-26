from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.spec.types import ReplayLineageMode


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
