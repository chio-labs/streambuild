"""Immutable request and result contracts for standard-mode builds."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterOwnershipRecord,
    AdapterReplayColumns,
    AdapterReplayCoverageRange,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import StandardPlan


@dataclass(frozen=True)
class StandardBuildRequest:
    """One complete instruction to realize a planned standard closure."""

    plan: StandardPlan
    realized_project: RealizedProject
    database: str
    metadata_database: str
    tool_version: str
    stabilization_seconds: float = 5.0
    boundary_time: str | None = None


@dataclass(frozen=True)
class PreservedSourceRealization:
    """Which managed source relations already existed and which were created."""

    preserved_relation_names: tuple[str, ...]
    created_relation_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardReplayBoundary:
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
class StandardReplayCoverage:
    """Durable replay ranges required to reproduce one standard model."""

    model_name: str
    driving_input_replay_columns: AdapterReplayColumns
    ranges: tuple[AdapterReplayCoverageRange, ...]


@dataclass(frozen=True)
class StandardPopulationResult:
    """Relations, boundaries, and models completed by ordered standard population."""

    created_view_relation_names: tuple[str, ...]
    boundaries: tuple[StandardReplayBoundary, ...]
    populated_model_names: tuple[str, ...]


@dataclass(frozen=True)
class StandardBuildResult:
    """Everything one standard build durably changed, in execution order."""

    database: str
    ownership_records: tuple[AdapterOwnershipRecord, ...]
    preserved_source_relation_names: tuple[str, ...]
    created_source_relation_names: tuple[str, ...]
    dropped_relation_names: tuple[str, ...]
    created_relation_names: tuple[str, ...]
    boundary_time: str
    boundaries: tuple[StandardReplayBoundary, ...]
    replayed_model_names: tuple[str, ...]
