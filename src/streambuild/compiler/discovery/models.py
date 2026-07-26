"""Authored specification models and the discovery results built from them."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from streambuild.compiler.discovery.constants import DEFAULT_ADAPTER_NAME
from streambuild.compiler.discovery.exceptions import ProjectSpecError
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SchemaChangeBackfillMode,
    SourceKind,
)


@dataclass(frozen=True)
class SchemaChangeBackfillRule:
    """One authored backfill preference for a schema change class."""

    mode: SchemaChangeBackfillMode | str
    lookback_seconds: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", SchemaChangeBackfillMode(self.mode))


@dataclass(frozen=True)
class SchemaChangeBackfillPolicy:
    """Optional authored policy for breaking vs non-breaking schema changes."""

    breaking: SchemaChangeBackfillRule | None = None
    non_breaking: SchemaChangeBackfillRule | None = None


@dataclass(frozen=True)
class KafkaSettings:
    """Kafka engine settings for a landing step."""

    broker_list: str
    topic: str
    consumer_group: str | None = None
    format: str = "JSONAsString"
    settings: dict[str, str] | None = None


@dataclass(frozen=True)
class KafkaLandingStep:
    """A standardized Kafka landing step."""

    name: str
    kafka: KafkaSettings


@dataclass(frozen=True)
class ReplayBoundaryColumns:
    """User-declared source boundary column mapping."""

    partition: str | None = None
    offset: str | None = None
    timestamp: str | None = None
    landed_at: str | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class ReplayBoundary:
    """User-declared replay boundary contract for an adopted source."""

    mode: ReplayBoundaryMode | str
    columns: ReplayBoundaryColumns

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ReplayBoundaryMode(self.mode))


@dataclass(frozen=True)
class ExternalTableSourceStep:
    """A replay-driving adopted source table."""

    name: str
    kind: SourceKind | str
    table_name: str
    replay_boundary: ReplayBoundary

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SourceKind(self.kind))


@dataclass(frozen=True)
class TransformStep:
    """A transform from one logical upstream node into a managed table."""

    name: str
    source: str
    engine: str
    order_by: list[str]
    query: str | None = None
    sql_file: str | None = None
    partition_by: str | None = None
    ttl: str | None = None
    settings: dict[str, str] | None = None
    replay_anchor: ReplayAnchorMode | str = ReplayAnchorMode.AUTO
    schema_change_backfill: SchemaChangeBackfillPolicy | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_anchor", ReplayAnchorMode(self.replay_anchor))
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )
        if bool(self.query) == bool(self.sql_file):
            raise ProjectSpecError("Exactly one of 'query' or 'sql_file' must be provided")
        if not self.order_by:
            raise ProjectSpecError("TransformStep must declare at least one ORDER BY expression")


@dataclass(frozen=True, repr=False)
class ProjectClickHouseConfig:
    """Optional project-level ClickHouse connection defaults."""

    host: str
    port: int
    username: str
    password: str


@dataclass(frozen=True)
class Project:
    """Project-level authored Streambuild config."""

    replay_lineage_mode: ReplayLineageMode | str = ReplayLineageMode.OFFSETS
    bounded_replay_fallback: BoundedReplayFallback | str = BoundedReplayFallback.FULL_REFRESH
    default_database: str | None = None
    clickhouse: ProjectClickHouseConfig | None = None
    version: int | None = None
    adapter: str = DEFAULT_ADAPTER_NAME

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_lineage_mode", ReplayLineageMode(self.replay_lineage_mode))
        object.__setattr__(
            self,
            "bounded_replay_fallback",
            BoundedReplayFallback(self.bounded_replay_fallback),
        )


@dataclass(frozen=True)
class Pipeline:
    """A single authored streaming pipeline."""

    name: str
    source: KafkaLandingStep | ExternalTableSourceStep
    transforms: list[TransformStep] = field(default_factory=list)
    replay_lineage_mode: ReplayLineageMode | str | None = None
    bounded_replay_fallback: BoundedReplayFallback | str | None = None

    def __post_init__(self) -> None:
        if self.replay_lineage_mode is not None:
            object.__setattr__(
                self,
                "replay_lineage_mode",
                ReplayLineageMode(self.replay_lineage_mode),
            )
        if self.bounded_replay_fallback is not None:
            object.__setattr__(
                self,
                "bounded_replay_fallback",
                BoundedReplayFallback(self.bounded_replay_fallback),
            )


@dataclass(frozen=True)
class LoadedPipeline:
    """A discovered pipeline plus the file it was loaded from."""

    pipeline: Pipeline
    file_path: Path
    project: Project | None = None
