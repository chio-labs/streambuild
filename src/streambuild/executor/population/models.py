"""Immutable contracts for mode-neutral replay population."""

from dataclasses import dataclass

from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    DesiredState,
    ExternalSourceReplayConfig,
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
class PopulationWatermarkInput:
    """Resolved physical input and adopted-source metadata for watermark capture."""

    table_name: str
    external_source_config: ExternalSourceReplayConfig | None


@dataclass(frozen=True)
class PopulationSourcePreparation:
    """Managed source resources preserved, created, and awaiting activation."""

    preserved_relation_names: tuple[str, ...]
    created_relation_names: tuple[str, ...]
    landing_views: tuple[DesiredMaterializedView, ...]


@dataclass(frozen=True)
class PopulationRequest:
    """Inputs for one shared physical population execution."""

    plan: PopulationPlan
    desired_state: DesiredState
    default_database: str
    source_preparation: PopulationSourcePreparation
    stabilization_seconds: float
    boundary_time: str | None = None
    watermark_metadata_database: str | None = None


@dataclass(frozen=True)
class PopulationReplayExecution:
    """One replay root actually submitted to the warehouse."""

    root_key: ObjectKey
    written_rows: int | None


@dataclass(frozen=True)
class PopulationResult:
    """Physical objects and replay roots completed by one population."""

    boundary_time: str
    created_relation_names: tuple[str, ...]
    preserved_source_relation_names: tuple[str, ...]
    created_source_relation_names: tuple[str, ...]
    watermarks: tuple[PopulationWatermark, ...]
    replay_executions: tuple[PopulationReplayExecution, ...]
    completed_root_keys: tuple[ObjectKey, ...]


@dataclass(frozen=True)
class OffsetWatermarkQueryRow:
    """One decoded partition cutoff row."""

    _replay_partition: object
    cutoff_offset: str
