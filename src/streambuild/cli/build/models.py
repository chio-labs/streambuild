"""Options and prepared contexts for the mode-aware build command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DeploymentPlan, DirectPlan
from streambuild.executor.backfill.models import BackfillBootstrapRequest, RootBackfillReport
from streambuild.executor.direct.models import DirectBuildRequest
from streambuild.executor.workflow.models import BuildWorkflow


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
class WorkflowPreparationOptions:
    """Connected planning options shared by `stb plan` and `stb build`."""

    database: str | None
    metadata_database: str | None
    selectors: tuple[str, ...]
    deployment_id: str | None
    full_refresh: bool
    start_time: str | None
    verbose: bool


@dataclass(frozen=True)
class DirectBuildPreviewContext:
    """The plan and resolved databases a build renders before it writes anything."""

    analysis: CompileAnalysis
    plan: DirectPlan
    database: str
    metadata_database: str
    adapter_name: str
    effective_start_time: str | None = None


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
    root_reports: tuple[RootBackfillReport, ...]
    existing_relation_names: frozenset[str]
    target_catalog: CatalogSnapshot
    metadata_catalog: CatalogSnapshot
    full_refresh_keys: frozenset[ObjectKey] = frozenset()
    start_time_keys: frozenset[ObjectKey] = frozenset()
    start_time: str | None = None


@dataclass(frozen=True)
class DirectWorkflowPreparation:
    """One fully assembled direct workflow and its result-decoding request."""

    preview: DirectBuildPreviewContext
    request: DirectBuildRequest
    workflow: BuildWorkflow
    plan_text: str


@dataclass(frozen=True)
class VirtualWorkflowPreparation:
    """One fully assembled virtual workflow and its result-decoding request."""

    preview: VirtualBuildPreviewContext
    request: BackfillBootstrapRequest
    workflow: BuildWorkflow
    plan_text: str
