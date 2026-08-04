"""Immutable request and result contracts for direct-mode builds."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import DirectPlan
from streambuild.executor.auditing.models import SqlAuditRunResult


@dataclass(frozen=True)
class DirectBuildRequest:
    """One complete instruction to realize a planned direct closure."""

    plan: DirectPlan
    realized_project: RealizedProject
    database: str
    metadata_database: str
    tool_version: str
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    stabilization_seconds: float = 5.0
    boundary_time: str | None = None
    audits: tuple[DirectBuildAudit, ...] = ()

    @property
    def effective_start_time(self) -> str | None:
        """Return the normalized lower bound carried by the confirmed plan."""

        return self.plan.effective_start_time


@dataclass(frozen=True)
class DirectBuildAudit:
    """One selected direct audit with refs resolved before workflow assembly."""

    name: str
    query: str
    severity: str
    description: str | None


@dataclass(frozen=True)
class DirectReplayBoundary:
    """One partition-scoped or scalar cutoff separating replay from live propagation."""

    model_name: str
    driving_input_relation_name: str
    replay_boundary_mode: ReplayLineageMode | str
    boundary_key: str
    cutoff_value: str
    cutoff_inclusive: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "replay_boundary_mode", ReplayLineageMode(self.replay_boundary_mode)
        )


@dataclass(frozen=True)
class DirectRootReplayResult:
    """One direct replay root actually executed in the warehouse."""

    model_name: str
    written_rows: int | None


@dataclass(frozen=True)
class DirectBuildResult:
    """Everything one direct build durably changed, in execution order."""

    database: str
    preserved_source_relation_names: tuple[str, ...]
    created_source_relation_names: tuple[str, ...]
    dropped_relation_names: tuple[str, ...]
    created_relation_names: tuple[str, ...]
    boundary_time: str
    boundaries: tuple[DirectReplayBoundary, ...]
    replay_results: tuple[DirectRootReplayResult, ...]
    effective_start_time: str | None = None


@dataclass(frozen=True)
class DirectBuildExecutionResult:
    """Direct build and audit evidence decoded from one workflow execution."""

    build_result: DirectBuildResult
    audit_result: SqlAuditRunResult
