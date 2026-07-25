from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.models import ObjectKey
from streambuild.spec.models.types import ReplayLineageMode


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


@dataclass(frozen=True)
class SelectionResolution:
    desired_state: DesiredState
    selected_model_keys: frozenset[ObjectKey]
    replay_lineage_mode: ReplayLineageMode


@dataclass(frozen=True)
class CompactChangedTargetSummary:
    target_name: str
    detail_lines: tuple[str, ...]
