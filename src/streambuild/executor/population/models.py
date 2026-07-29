"""Immutable contracts for mode-neutral replay population."""

from dataclasses import dataclass

from streambuild.compiler.compile.models import DesiredState, ObjectKey
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
class PopulationRequest:
    """Inputs for one shared physical population execution."""

    plan: PopulationPlan
    desired_state: DesiredState
    default_database: str
    stabilization_seconds: float
    boundary_time: str | None = None
    watermark_metadata_database: str | None = None


@dataclass(frozen=True)
class PopulationResult:
    """Physical objects and replay roots completed by one population."""

    boundary_time: str
    created_relation_names: tuple[str, ...]
    watermarks: tuple[PopulationWatermark, ...]
    replayed_root_keys: tuple[ObjectKey, ...]


@dataclass(frozen=True)
class OffsetWatermarkQueryRow:
    """One decoded partition cutoff row."""

    _replay_partition: object
    cutoff_offset: str
