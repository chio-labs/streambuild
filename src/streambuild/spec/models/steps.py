"""Step models for authored pipeline specifications."""

from dataclasses import dataclass

from streambuild.spec.models.exceptions import ProjectSpecError
from streambuild.spec.models.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayBoundaryMode,
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
