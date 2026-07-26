"""Neutral adapter identity, connection, and result models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from streambuild.adapter.constants import REDACTED_SECRET_PLACEHOLDER
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.types import (
    AdapterReplayBoundaryMode,
    AdapterReplayLowerBoundMode,
    AdapterReplaySeedMode,
)


@dataclass(frozen=True)
class AdapterIdentity:
    """The registered name of one adapter implementation."""

    name: str


@dataclass(frozen=True)
class AdapterCapabilities:
    """Capabilities implemented by one adapter."""

    virtual_environments: bool
    managed_source_kinds: frozenset[str]
    replay_boundary_modes: frozenset[AdapterReplayBoundaryMode]
    history_prefix_seed: bool


@dataclass(frozen=True)
class AdapterColumn:
    """One column in a neutral adapter resource request."""

    name: str
    type: str
    default_expression: str | None = None


@dataclass(frozen=True)
class AdapterManagedSource:
    """A managed streaming source to realize in a warehouse."""

    source_kind: str
    name: str
    columns: tuple[AdapterColumn, ...]
    broker_list: str
    topic: str
    consumer_group: str
    format: str
    settings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AdapterTable:
    """A managed table to realize in a warehouse."""

    name: str
    columns: tuple[AdapterColumn, ...]
    engine: str
    order_by: tuple[str, ...]
    partition_by: str | None = None
    ttl: str | None = None
    settings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AdapterMaterializedView:
    """A materialized view to realize between warehouse relations."""

    name: str
    source_relation_name: str
    target_relation_name: str
    query: str


@dataclass(frozen=True)
class AdapterStableView:
    """A stable logical view to bind to one physical relation."""

    name: str
    target_relation_name: str


@dataclass(frozen=True)
class AdapterPhysicalRelationMapping:
    """A logical relation mapped to its replay-time physical relation."""

    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class AdapterReplayQuery:
    """A compiler-analyzed query ready for adapter replay realization."""

    query: str
    physical_relation_mappings: tuple[AdapterPhysicalRelationMapping, ...]
    aggregate_semantics: bool


@dataclass(frozen=True)
class AdapterReplayBoundary:
    """One inclusive replay cutoff, optionally scoped to a partition."""

    boundary_key: str
    cutoff_value: str
    cutoff_inclusive: bool
    partition_value: str | None = None


@dataclass(frozen=True)
class AdapterReplayColumns:
    """Physical boundary columns used to read an anchor relation."""

    partition: str
    offset: str
    timestamp: str
    landed_at: str
    cursor: str


@dataclass(frozen=True)
class AdapterReplayWindow:
    """The lower-bound policy for one replay root."""

    lower_bound_mode: AdapterReplayLowerBoundMode
    lower_bound_inclusive: bool
    boundary_time: str
    forced_start_time: str | None
    lookback_seconds: int | None


@dataclass(frozen=True)
class AdapterReplayRelations:
    """Logical and physical relations participating in one replay root."""

    root: str
    source: str
    anchor: str
    target: str


@dataclass(frozen=True)
class AdapterReplayRequest:
    """A mode-neutral request to seed and replay one rebuild root."""

    mode: AdapterReplayBoundaryMode
    database: str
    relations: AdapterReplayRelations
    replay_query: AdapterReplayQuery
    boundaries: tuple[AdapterReplayBoundary, ...]
    columns: AdapterReplayColumns
    window: AdapterReplayWindow
    seed_mode: AdapterReplaySeedMode
    target_column_names: tuple[str, ...]


@dataclass(frozen=True)
class AdapterMetadataObjectKey:
    """A logical object identity stored in framework metadata."""

    database: str | None
    object_type: str
    name: str


@dataclass(frozen=True)
class AdapterPreparedObjectMapping:
    """A persisted logical-to-physical object mapping."""

    logical_key: AdapterMetadataObjectKey
    physical_name: str


@dataclass(frozen=True)
class AdapterObjectStateRecord:
    """One adapter-neutral object-state metadata record."""

    deployment_id: str
    key: AdapterMetadataObjectKey
    normalized_fingerprint: str
    normalized_query: str | None
    recorded_at: str


@dataclass(frozen=True)
class AdapterDeploymentRecord:
    """One adapter-neutral staged deployment record."""

    deployment_id: str
    created_at: str
    status: str
    replay_lineage_mode: str
    selected_root_keys: tuple[AdapterMetadataObjectKey, ...]
    warning_codes: tuple[str, ...]
    prepared_object_mappings: tuple[AdapterPreparedObjectMapping, ...]


@dataclass(frozen=True)
class AdapterDeploymentWatermarkRecord:
    """One adapter-neutral replay watermark record."""

    deployment_id: str
    root_key: AdapterMetadataObjectKey
    anchor_key: AdapterMetadataObjectKey
    boundary_key: str
    cutoff_value: str


@dataclass(frozen=True)
class AdapterDeploymentRuntimeDetailRecord:
    """One adapter-neutral deployment runtime-detail record."""

    deployment_id: str
    root_key: AdapterMetadataObjectKey
    state_kind: str
    replay_strategy: str
    active_deployment_id: str | None
    anchor_key: AdapterMetadataObjectKey
    anchor_physical_name: str | None
    execution_mode: str | None
    configured_backfill_mode: str | None
    execution_lookback_seconds: int | None
    live_target_names: tuple[str, ...]


@dataclass(frozen=True)
class AdapterPublishEventRecord:
    """One adapter-neutral publish-history record."""

    deployment_id: str
    published_at: str
    logical_view_names: tuple[str, ...]


@dataclass(frozen=True)
class AdapterMetadataState:
    """A batch of framework metadata records for adapter persistence."""

    object_states: tuple[AdapterObjectStateRecord, ...]
    deployments: tuple[AdapterDeploymentRecord, ...]
    deployment_watermarks: tuple[AdapterDeploymentWatermarkRecord, ...]
    deployment_runtime_details: tuple[AdapterDeploymentRuntimeDetailRecord, ...]
    publish_events: tuple[AdapterPublishEventRecord, ...]


@dataclass(frozen=True)
class CatalogIdentity:
    """Stable identity of one adapter/database catalog observation."""

    adapter: AdapterIdentity
    database: str


@dataclass(frozen=True)
class CatalogColumn:
    """One warehouse relation column observed by an adapter."""

    name: str
    type: str
    default_expression: str | None = None


@dataclass(frozen=True)
class CatalogRelation:
    """One immutable warehouse relation observation."""

    name: str
    engine: str
    columns: tuple[CatalogColumn, ...]
    order_by: tuple[str, ...] = ()
    partition_by: str | None = None
    ttl: str | None = None
    settings: tuple[tuple[str, str], ...] = ()
    definition_sql: str | None = None
    query_sql: str | None = None
    source_relation_name: str | None = None
    target_relation_name: str | None = None
    stable_binding_name: str | None = None


@dataclass(frozen=True)
class CatalogSnapshot:
    """One immutable point-in-time catalog for an adapter and database."""

    identity: CatalogIdentity
    warehouse_timezone: str
    relations: tuple[CatalogRelation, ...]

    def relation(self, name: str) -> CatalogRelation | None:
        """Return one relation by unqualified name when it exists."""

        return next((relation for relation in self.relations if relation.name == name), None)

    def relation_names(self) -> frozenset[str]:
        """Return every observed unqualified relation name."""

        return frozenset(relation.name for relation in self.relations)


@dataclass(frozen=True)
class InspectedActiveTableBinding:
    """A stable logical view pointing at an active physical table."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class InspectedPhysicalTableCandidate:
    """A deployment-suffixed physical table candidate for a logical root."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class InspectedManagedTableState:
    """Managed table state used for active-deployment resolution."""

    active_bindings: tuple[InspectedActiveTableBinding, ...]
    physical_candidates: tuple[InspectedPhysicalTableCandidate, ...]


@dataclass(frozen=True, repr=False)
class AdapterConnectionConfig:
    """Resolved, format-neutral connection settings for one adapter."""

    host: str
    port: int
    username: str
    password: str
    database: str | None = None

    def __repr__(self) -> str:
        """Render the configuration without exposing the password."""

        return (
            f"{type(self).__name__}(host={self.host!r}, port={self.port!r}, "
            f"username={self.username!r}, password={REDACTED_SECRET_PLACEHOLDER!r}, "
            f"database={self.database!r})"
        )


@dataclass(frozen=True)
class AdapterQueryResult:
    """A normalized query result returned by the adapter boundary."""

    rows: tuple[tuple[object, ...], ...]
    column_names: tuple[str, ...] = ()

    def named_rows(self) -> tuple[Mapping[str, object], ...]:
        """Return rows keyed by the query's column names."""

        if not self.column_names:
            if not self.rows:
                return ()
            raise AdapterResultError("Query result does not include column names")
        return tuple(dict(zip(self.column_names, row, strict=True)) for row in self.rows)
