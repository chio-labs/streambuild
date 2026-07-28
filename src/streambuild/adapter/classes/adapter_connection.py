"""Neutral warehouse connection contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterCapabilities,
    AdapterDeploymentInventory,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterOwnershipRecord,
    AdapterQueryResult,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterRelationCleanupRequest,
    AdapterRelationCleanupResult,
    AdapterReplayRequest,
    AdapterStableView,
    AdapterTable,
    CatalogSnapshot,
    InspectedManagedTableState,
)


class AdapterConnection(ABC):
    """An open warehouse connection exposing neutral statements and results."""

    @property
    @abstractmethod
    def adapter_identity(self) -> AdapterIdentity:
        """Return the identity of the adapter that owns this connection."""

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Return the capabilities implemented by this connection's adapter."""

    @abstractmethod
    def load_catalog(self, database: str) -> CatalogSnapshot:
        """Load one immutable catalog snapshot for a database."""

    @abstractmethod
    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        """Return the currently available columns for one framework metadata table."""

    @abstractmethod
    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        """Inspect stable bindings and deployment-specific physical relations."""

    @abstractmethod
    def load_target_ownership(self, database: str) -> tuple[AdapterOwnershipRecord, ...]:
        """Load every durable StreamBuild ownership record for one database."""

    @abstractmethod
    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        """Durably claim every requested relation before it is created or replaced."""

    @abstractmethod
    def command(self, statement: str) -> None:
        """Execute a statement that returns no result rows."""

    @abstractmethod
    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a query and return its normalized result."""

    @abstractmethod
    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        """Insert row mappings into a warehouse table."""

    @abstractmethod
    def ensure_database(self, database: str) -> None:
        """Create a database when it does not already exist."""

    @abstractmethod
    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        """Render one neutral resource request into adapter SQL."""

    @abstractmethod
    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        """Realize one neutral resource request in the warehouse."""

    @abstractmethod
    def migrate_metadata_state(self, database: str) -> None:
        """Apply pending additive framework metadata migrations."""

    @abstractmethod
    def persist_metadata_state(self, *, database: str, state: AdapterMetadataState) -> None:
        """Persist one batch of adapter-neutral framework metadata."""

    @abstractmethod
    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        """Load persisted deployments and publish events for lifecycle cleanup."""

    @abstractmethod
    def execute_replay(self, request: AdapterReplayRequest) -> None:
        """Seed and replay one mode-neutral rebuild-root request."""

    @abstractmethod
    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        """Compare live and staged relations for publish readiness."""

    @abstractmethod
    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        """Replace stable logical bindings and report actual atomicity."""

    @abstractmethod
    def cleanup_relations(
        self, request: AdapterRelationCleanupRequest
    ) -> AdapterRelationCleanupResult:
        """Remove requested physical relations and report the completed cleanup."""

    @abstractmethod
    def close(self) -> None:
        """Close the underlying connection."""

    def query_many[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> tuple[DecodedRow, ...]:
        """Execute a query and decode every row into a typed object."""

        result: AdapterQueryResult = self.query(statement)
        return tuple(decode(row) for row in result.named_rows())

    def query_one[DecodedRow](
        self,
        *,
        statement: str,
        decode: Callable[[Mapping[str, object]], DecodedRow],
    ) -> DecodedRow | None:
        """Execute a query and decode the first row if one exists."""

        rows: tuple[DecodedRow, ...] = self.query_many(statement=statement, decode=decode)
        return rows[0] if rows else None
