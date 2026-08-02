"""Neutral warehouse connection contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping

from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterCapabilities,
    AdapterDeploymentInventory,
    AdapterDeploymentReplayRequest,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterMutationResult,
    AdapterOwnershipRecord,
    AdapterOwnershipReplayRequest,
    AdapterQueryResult,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterRelationCleanupRequest,
    AdapterStableView,
    AdapterTable,
    AdapterView,
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
    def render_record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> tuple[str, ...]:
        """Render exact SQL that durably claims the requested relations."""

    @abstractmethod
    def render_remove_target_ownership(
        self,
        *,
        database: str,
        target_database: str,
        relation_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Render exact SQL that removes retired relation claims."""

    @abstractmethod
    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a query and return its normalized result."""

    @abstractmethod
    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        """Execute exact workflow mutation SQL and return warehouse evidence."""

    @abstractmethod
    def capture_warehouse_timestamp(self) -> str:
        """Capture the active warehouse server's UTC millisecond timestamp."""

    @abstractmethod
    def render_ensure_database(self, database: str) -> str:
        """Render exact SQL that creates a database when needed."""

    @abstractmethod
    def render_resource(
        self,
        *,
        resource: (
            AdapterManagedSource
            | AdapterTable
            | AdapterMaterializedView
            | AdapterView
            | AdapterStableView
        ),
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        """Render one neutral resource request into adapter SQL."""

    @abstractmethod
    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        """Render exact SQL for the current additive metadata migration."""

    @abstractmethod
    def render_persist_metadata_state(
        self, *, database: str, state: AdapterMetadataState
    ) -> tuple[str, ...]:
        """Render exact SQL that persists adapter-neutral metadata."""

    @abstractmethod
    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        """Load persisted deployments and publish events for lifecycle cleanup."""

    @abstractmethod
    def render_replay_from_ownership(self, request: AdapterOwnershipReplayRequest) -> str:
        """Render one replay that reads its boundary from durable ownership metadata."""

    def render_replay_from_deployment(
        self, request: AdapterDeploymentReplayRequest
    ) -> tuple[str, ...]:
        """Render fixed-cardinality seed and replay SQL from deployment metadata."""

        del request
        raise AdapterCapabilityError(
            f"Adapter '{self.adapter_identity.name}' cannot render deployment replay SQL"
        )

    @abstractmethod
    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        """Compare live and staged relations for publish readiness."""

    @abstractmethod
    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        """Render exact SQL that replaces and removes stable logical bindings."""

    @abstractmethod
    def render_cleanup_relations(self, request: AdapterRelationCleanupRequest) -> tuple[str, ...]:
        """Render guarded SQL that removes requested physical relations."""

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
