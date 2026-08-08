"""Immutable contracts for mode-neutral replay population."""

from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterStableView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    ObjectKey,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.types import RebuildExecutionMode


@dataclass(frozen=True)
class PopulationRoot:
    """One replay root and its physical propagation scope."""

    root_key: ObjectKey
    affected_keys: tuple[ObjectKey, ...]
    upstream_boundary_key: ObjectKey
    replay_lineage_mode: ReplayLineageMode | str
    execution_mode: RebuildExecutionMode | str = RebuildExecutionMode.FULL_REBUILD
    forced_start_time: str | None = None
    execution_lookback_seconds: int | None = None
    persist_watermarks: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))
        object.__setattr__(self, "execution_mode", RebuildExecutionMode(self.execution_mode))


@dataclass(frozen=True)
class PopulationObject:
    """One logical object mapped to its execution-time physical name."""

    logical_key: ObjectKey
    physical_name: str


@dataclass(frozen=True)
class PopulationPlan:
    """The complete mode-neutral physical population instruction."""

    execution_id: str
    roots: tuple[PopulationRoot, ...]
    objects: tuple[PopulationObject, ...]


@dataclass(frozen=True)
class PopulationWatermark:
    """One inclusive replay cutoff for a population root."""

    root_key: ObjectKey
    anchor_key: ObjectKey
    boundary_key: str
    cutoff_value: str


@dataclass(frozen=True)
class PopulationManagedSource:
    """One complete managed-source definition used during source preparation."""

    resource: AdapterManagedSource
    database: str


@dataclass(frozen=True)
class PopulationRealization:
    """One population resource ready for render-only warehouse realization."""

    resource: (
        AdapterManagedSource
        | AdapterTable
        | AdapterMaterializedView
        | AdapterView
        | AdapterStableView
    )
    database: str


@dataclass(frozen=True)
class PopulationSourcePreparation:
    """Managed source resources preserved, created, and awaiting activation."""

    preserved_relation_names: tuple[str, ...]
    created_relation_names: tuple[str, ...]
    landing_views: tuple[DesiredMaterializedView, ...]
    managed_sources: tuple[PopulationManagedSource, ...]
