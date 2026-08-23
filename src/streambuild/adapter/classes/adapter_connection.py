"""Neutral warehouse connection contract."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping

from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterCapabilities,
    AdapterCapturedReplayRequest,
    AdapterCurrentQualityNode,
    AdapterDeploymentInventory,
    AdapterDeploymentReplayRequest,
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    AdapterIdentity,
    AdapterInvocationRecord,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterMutationResult,
    AdapterNodeResultRecord,
    AdapterQueryResult,
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterRefreshState,
    AdapterRelationCleanupRequest,
    AdapterReplayCoverageRequest,
    AdapterRunEventRecord,
    AdapterRunStatementRecord,
    AdapterSensorState,
    AdapterStableView,
    AdapterStatementProgress,
    AdapterTable,
    AdapterView,
    AdapterWarehouseHealth,
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

    def load_refresh_states(self, database: str) -> tuple[AdapterRefreshState, ...]:
        """Report scheduled refresh state; adapters without scheduled relations report none."""

        return ()

    @abstractmethod
    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        """Return the currently available columns for one framework metadata table."""

    def validate_metadata_state(self, database: str) -> None:
        """Fail when existing framework metadata is incompatible with this release."""

        del database

    @abstractmethod
    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        """Inspect stable bindings and deployment-specific physical relations."""

    @abstractmethod
    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a query and return its normalized result."""

    @abstractmethod
    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        """Execute exact workflow mutation SQL and return warehouse evidence."""

    def execute_workflow_query(self, *, statement: str, query_id: str | None) -> AdapterQueryResult:
        """Execute a workflow query with optional adapter-specific correlation."""

        del query_id
        return self.query(statement)

    def execute_workflow_mutation(
        self, *, statement: str, query_id: str | None
    ) -> AdapterMutationResult:
        """Execute a workflow mutation with optional adapter-specific correlation."""

        del query_id
        return self.execute_workflow_sql(statement)

    def load_statement_progress(self, *, query_id: str) -> AdapterStatementProgress | None:
        """Return ephemeral telemetry when the adapter exposes active-query progress."""

        del query_id
        return None

    @abstractmethod
    def capture_warehouse_timestamp(self) -> str:
        """Capture the active warehouse server's UTC millisecond timestamp."""

    def load_warehouse_health(self, database: str) -> AdapterWarehouseHealth:
        """Return optional adapter-neutral warehouse diagnostics."""

        del database
        return AdapterWarehouseHealth(
            availability="unavailable",
            status="unknown",
            version=None,
            uptime_seconds=None,
            disks=(),
            inode_total=None,
            inode_free=None,
            inode_status="unknown",
            memory=None,
            activity=None,
            tables=(),
            collection_duration_ms=0,
            warnings=(
                f"Adapter '{self.adapter_identity.name}' does not expose warehouse diagnostics",
            ),
        )

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

    def render_terminal_observations(
        self,
        *,
        database: str,
        invocation: AdapterInvocationRecord,
        node_results: tuple[AdapterNodeResultRecord, ...],
    ) -> tuple[str, ...]:
        """Render non-authoritative terminal observations when supported."""

        return ()

    def render_latest_node_status_query(
        self,
        *,
        database: str,
        project_identity: str,
        target_identity: str,
        nodes: tuple[AdapterCurrentQualityNode, ...],
    ) -> str:
        """Render the current-manifest quality status query when supported."""

        return ""

    def render_run_events(
        self,
        *,
        database: str,
        events: tuple[AdapterRunEventRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render incremental run-event inserts when supported."""

        return ()

    def render_run_statements(
        self,
        *,
        database: str,
        statements: tuple[AdapterRunStatementRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render durable run-statement inserts when supported."""

        return ()

    def render_sensor_state(
        self,
        *,
        database: str,
        state: AdapterSensorState,
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render incremental sensor-state inserts when supported."""

        return ()

    def render_sensor_retention_cleanup(
        self, *, database: str, retention_days: int
    ) -> tuple[str, ...]:
        """Render tick and step retention deletes when supported."""

        return ()

    def load_direct_fingerprints(
        self, *, database: str, logical_model_identities: tuple[str, ...]
    ) -> AdapterDirectFingerprintSnapshot:
        """Load optional logical direct SQL baselines when supported."""

        del database, logical_model_identities
        return AdapterDirectFingerprintSnapshot(
            status="unavailable",
            baselines=(),
            warning=f"Adapter '{self.adapter_identity.name}' does not expose direct SQL baselines",
        )

    def render_direct_fingerprint_observations(
        self,
        *,
        database: str,
        fingerprints: tuple[AdapterDirectFingerprintRecord, ...],
    ) -> tuple[str, ...]:
        """Render optional terminal logical SQL baseline writes when supported."""

        del database, fingerprints
        return ()

    @abstractmethod
    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        """Load persisted deployments and publish events for lifecycle cleanup."""

    @abstractmethod
    def render_replay_coverage_query(self, request: AdapterReplayCoverageRequest) -> str:
        """Render one query returning typed replay-window coverage rows."""

    def render_replay_from_capture(self, request: AdapterCapturedReplayRequest) -> str:
        """Render one replay from boundaries owned by the current process."""

        del request
        raise AdapterCapabilityError(
            f"Adapter '{self.adapter_identity.name}' cannot render captured replay SQL"
        )

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
