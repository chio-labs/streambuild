"""Compile-specific runtime models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    ObjectKey,
)
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.project import Project
from streambuild.spec.models.steps import ExternalTableSourceStep, TransformStep
from streambuild.spec.models.types import (
    BoundedReplayFallback,
    RefType,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
    SqlRelationType,
)


@dataclass(frozen=True)
class ParsedRef:
    """A parsed logical `__source(...)` or `__ref(...)` occurrence from transform SQL."""

    name: str
    relation_type: SqlRelationType | str
    ref_type: RefType | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", SqlRelationType(self.relation_type))


@dataclass(frozen=True)
class CompiledTransformStep:
    """Compiled transform information for the first compiler pass."""

    transform: TransformStep
    parsed_refs: tuple[ParsedRef, ...]
    resolved_query: str
    refs: tuple[str, ...]
    has_mutable_refs: bool
    has_aggregate_semantics: bool
    preserves_required_lineage: bool
    replay_anchor_eligible: bool
    effective_bounded_replay_fallback: BoundedReplayFallback
    target_table: DesiredTable
    materialized_view: DesiredMaterializedView
    target_table_name: str


@dataclass(frozen=True)
class CompiledManagedSource:
    """Compiled managed Kafka source objects for a pipeline."""

    kafka_table: DesiredKafkaTable
    raw_table: DesiredTable
    materialized_view: DesiredMaterializedView


@dataclass(frozen=True)
class CompiledExternalSource:
    """Compiled adopted replay-driving source metadata."""

    source: ExternalTableSourceStep
    source_key: ObjectKey


@dataclass(frozen=True)
class ExternalSourceReplayConfig:
    """Replay metadata for one adopted external source root."""

    key: ObjectKey
    table_name: str
    source_kind: SourceKind | str
    replay_boundary_mode: ReplayBoundaryMode | str
    partition_column_name: str | None = None
    offset_column_name: str | None = None
    timestamp_column_name: str | None = None
    landed_at_column_name: str | None = None
    cursor_column_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", SourceKind(self.source_kind))
        object.__setattr__(
            self, "replay_boundary_mode", ReplayBoundaryMode(self.replay_boundary_mode)
        )


@dataclass(frozen=True)
class CompiledPipeline:
    """Compiled representation of a pipeline's desired state."""

    pipeline: Pipeline
    project: Project | None
    file_path: Path
    relation_names: dict[str, str]
    relation_sqls: dict[str, str]
    effective_replay_lineage_mode: ReplayLineageMode
    source: CompiledManagedSource | CompiledExternalSource
    transforms: tuple[CompiledTransformStep, ...]


@dataclass(frozen=True)
class DesiredState:
    """Project-level flat desired object graph."""

    objects: tuple[DesiredKafkaTable | DesiredTable | DesiredMaterializedView, ...]
    replay_anchor_keys: frozenset[ObjectKey]
    mutable_ref_warning_keys: frozenset[ObjectKey]
    external_source_replay_configs: tuple[ExternalSourceReplayConfig, ...] = ()
