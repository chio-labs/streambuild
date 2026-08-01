"""Options and prepared contexts for the mode-aware build command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DeploymentPlan, DirectPlan


@dataclass(frozen=True)
class BuildCommandOptions:
    """Every operator-supplied option for one `stb build` invocation."""

    pipelines_root: Path
    database: str | None
    metadata_database: str | None
    selectors: tuple[str, ...]
    json_output: bool
    verbose: bool
    auto_approve: bool
    deployment_id: str | None = None
    full_refresh: bool = False
    start_time: str | None = None


@dataclass(frozen=True)
class DirectBuildPreviewContext:
    """The plan and resolved databases a build renders before it writes anything."""

    analysis: CompileAnalysis
    plan: DirectPlan
    database: str
    metadata_database: str
    adapter_name: str


@dataclass(frozen=True)
class VirtualBuildPreviewContext:
    """The confirmed virtual deployment plan and its fixed execution identity."""

    database: str
    metadata_database: str
    desired_state: DesiredState
    plan: DeploymentPlan
    replay_lineage_mode: ReplayLineageMode
    deployment_id: str
    created_at: str
    full_refresh_keys: frozenset[ObjectKey] = frozenset()
    start_time_keys: frozenset[ObjectKey] = frozenset()
    start_time: str | None = None
