"""Backfill executor runtime models."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import DeploymentPlan


@dataclass(frozen=True)
class BackfillBootstrapRequest:
    """Input required to bootstrap a staged backfill deployment."""

    desired_state: DesiredState
    default_database: str
    metadata_database: str
    replay_lineage_mode: ReplayLineageMode | str
    deployment_id: str | None = None
    full_refresh_keys: frozenset[ObjectKey] = frozenset()
    start_time_keys: frozenset[ObjectKey] = frozenset()
    start_time: str | None = None
    created_at: str | None = None
    boundary_time: str | None = None
    stabilization_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))


@dataclass(frozen=True)
class BackfillBootstrapResult:
    """Result of bootstrapping a staged backfill deployment."""

    deployment_id: str
    created_at: str
    deployment_plan: DeploymentPlan
    root_reports: tuple[RootBackfillReport, ...]


@dataclass(frozen=True)
class BackfillExecutionResult:
    """Result of executing a staged backfill through boundary capture and replay."""

    bootstrap: BackfillBootstrapResult
    boundary_time: str


@dataclass(frozen=True)
class RootBackfillReport:
    """User-facing rebuild strategy report for one managed root."""

    root_key: ObjectKey
    state_kind: str
    replay_strategy: str
    active_deployment_id: str | None


@dataclass(frozen=True)
class OffsetWatermarkQueryRow:
    """Row shape for per-partition offset watermark queries."""

    _replay_partition: object
    cutoff_offset: str


@dataclass(frozen=True)
class TableColumnSystemRow:
    """Row shape for system column inspection during backfill execution."""

    name: str
    type: str


@dataclass(frozen=True)
class ActiveScalarFrontierQueryRow:
    """Row shape for the current active scalar replay frontier."""

    cutoff_value: str | None


@dataclass(frozen=True)
class CursorLowerBoundQueryRow:
    """Row shape for cursor lower-bound lookup from _replay_timestamp."""

    lower_bound_cursor: str | None


@dataclass(frozen=True)
class ActiveOffsetFrontierQueryRow:
    """Row shape for the current active per-partition offset frontier."""

    _replay_partition: object
    cutoff_offset: str
