"""Neutral adapter identity, connection, and result models."""

from collections.abc import Mapping
from dataclasses import dataclass

from streambuild.adapter.constants import REDACTED_SECRET_PLACEHOLDER
from streambuild.adapter.exceptions import AdapterResultError


@dataclass(frozen=True)
class AdapterIdentity:
    """The registered name of one adapter implementation."""

    name: str


@dataclass(frozen=True)
class AdapterCapabilities:
    """Capabilities implemented by one adapter."""

    virtual_environments: bool


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
