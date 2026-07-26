"""Compile-specific runtime models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.spec.models import (
    ExternalTableSourceStep,
    Pipeline,
    Project,
    SchemaChangeBackfillPolicy,
    TransformStep,
)
from streambuild.spec.types import (
    BoundedReplayFallback,
    RefType,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
    SqlRelationType,
)


@dataclass(frozen=True)
class ObjectKey:
    """Stable identity for a comparable deployed object."""

    database: str | None
    object_type: DesiredObjectType | str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_type", DesiredObjectType(self.object_type))


@dataclass(frozen=True)
class Column:
    """A normalized comparable column definition."""

    name: str
    type: str
    default: str | None = None


@dataclass(frozen=True)
class KafkaSettings:
    """Normalized comparable Kafka engine settings."""

    broker_list: str
    topic: str
    consumer_group: str
    format: str
    settings: dict[str, str] | None = None


@dataclass(frozen=True)
class KafkaTableSpec:
    """Comparable Kafka table specification."""

    columns: tuple[Column, ...]
    kafka: KafkaSettings


@dataclass(frozen=True)
class TableStorage:
    """Comparable managed-table storage definition."""

    engine: str
    order_by: tuple[str, ...]
    partition_by: str | None = None
    ttl: str | None = None
    settings: dict[str, str] | None = None


@dataclass(frozen=True)
class TableSpec:
    """Comparable managed-table specification."""

    columns: tuple[Column, ...]
    storage: TableStorage


@dataclass(frozen=True)
class MaterializedViewSpec:
    """Comparable materialized-view specification."""

    source_table_name: str
    target_table_name: str
    query: str


@dataclass(frozen=True)
class DesiredKafkaTable:
    """A desired Kafka engine table for a landing step."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
    spec: KafkaTableSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def kafka(self) -> KafkaSettings:
        return self.spec.kafka


@dataclass(frozen=True)
class DesiredTable:
    """A desired managed ClickHouse table."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
    spec: TableSpec
    schema_change_backfill: SchemaChangeBackfillPolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback = BoundedReplayFallback(
        BoundedReplayFallback.FULL_REFRESH
    )

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def columns(self) -> tuple[Column, ...]:
        return self.spec.columns

    @property
    def engine(self) -> str:
        return self.spec.storage.engine

    @property
    def order_by(self) -> tuple[str, ...]:
        return self.spec.storage.order_by

    @property
    def partition_by(self) -> str | None:
        return self.spec.storage.partition_by

    @property
    def ttl(self) -> str | None:
        return self.spec.storage.ttl

    @property
    def settings(self) -> dict[str, str] | None:
        return self.spec.storage.settings


@dataclass(frozen=True)
class DesiredMaterializedView:
    """A desired materialized view between a source and target relation."""

    key: ObjectKey
    deps: tuple[ObjectKey, ...]
    spec: MaterializedViewSpec

    @property
    def name(self) -> str:
        return self.key.name

    @property
    def source_table_name(self) -> str:
        return self.spec.source_table_name

    @property
    def target_table_name(self) -> str:
        return self.spec.target_table_name

    @property
    def query(self) -> str:
        return self.spec.query


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
