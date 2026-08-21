"""ClickHouse-backed implementation of the neutral connection contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from clickhouse_connect.driver.exceptions import ClickHouseError, StreamFailureError
from clickhouse_connect.driver.summary import QuerySummary

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import METADATA_NODE_RESULTS_TABLE_NAME
from streambuild.adapter.exceptions import AdapterResultError, AdapterWarehouseError
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
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse._helpers.errors import translate_driver_error
from streambuild.adapters.clickhouse._helpers.inspection import (
    load_clickhouse_catalog,
    load_clickhouse_refresh_states,
)
from streambuild.adapters.clickhouse._helpers.lifecycle import (
    load_clickhouse_deployment_inventory,
    render_clickhouse_relation_cleanup,
    render_clickhouse_stable_binding_replacement,
)
from streambuild.adapters.clickhouse._helpers.managed_tables import (
    build_inspected_managed_table_state,
)
from streambuild.adapters.clickhouse._helpers.metadata import (
    load_clickhouse_direct_fingerprints,
    render_clickhouse_direct_fingerprint_observations,
    render_clickhouse_latest_node_status_query,
    render_clickhouse_metadata_migration_workflow,
    render_clickhouse_metadata_state,
    render_clickhouse_run_event_inserts,
    render_clickhouse_run_statement_inserts,
    render_clickhouse_sensor_retention_cleanup,
    render_clickhouse_sensor_state_inserts,
)
from streambuild.adapters.clickhouse._helpers.readiness import compare_clickhouse_readiness
from streambuild.adapters.clickhouse._helpers.rendering import (
    render_clickhouse_ensure_database,
    render_clickhouse_resource,
)
from streambuild.adapters.clickhouse._helpers.replay import (
    render_clickhouse_replay_coverage_query,
    render_clickhouse_replay_from_capture,
    render_clickhouse_replay_from_deployment,
)
from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_ADAPTER_NAME,
    CLICKHOUSE_DIRECT_REBUILD_SUPPORTED,
    CLICKHOUSE_GRAPH_ATOMIC_PUBLISH,
    CLICKHOUSE_HISTORY_PREFIX_SEED_SUPPORTED,
    CLICKHOUSE_MANAGED_SOURCE_KINDS,
    CLICKHOUSE_PER_RELATION_ATOMIC_REPLACE,
    CLICKHOUSE_REPLAY_BOUNDARY_MODES,
    CLICKHOUSE_SET_DIFFERENCE_COMPARISON_SUPPORTED,
    CLICKHOUSE_STABLE_LOGICAL_BINDINGS_SUPPORTED,
    CLICKHOUSE_VIRTUAL_ENVIRONMENTS_SUPPORTED,
    CLICKHOUSE_WRITTEN_ROWS_SUMMARY_KEY,
)
from streambuild.adapters.clickhouse.types import (
    RawClickHouseClient,
    RawClickHouseQueryResult,
)

_NODE_RESULT_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "node_name",
        "binding_key",
        "definition_fingerprint",
        "execution_fingerprint",
        "trigger",
        "scheduled_for",
        "cadence_seconds",
        "warmup_seconds",
    }
)
_QUERY_ID_SETTING: str = "query_id"


class ClickHouseConnection(AdapterConnection):
    """A neutral adapter connection backed by the ClickHouse driver."""

    def __init__(self, raw_client: RawClickHouseClient) -> None:
        self._raw_client: RawClickHouseClient = raw_client

    @property
    def adapter_identity(self) -> AdapterIdentity:
        """Return the built-in ClickHouse adapter identity."""

        return AdapterIdentity(name=CLICKHOUSE_ADAPTER_NAME)

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return capabilities implemented by the ClickHouse adapter."""

        return AdapterCapabilities(
            virtual_environments=CLICKHOUSE_VIRTUAL_ENVIRONMENTS_SUPPORTED,
            managed_source_kinds=CLICKHOUSE_MANAGED_SOURCE_KINDS,
            replay_boundary_modes=CLICKHOUSE_REPLAY_BOUNDARY_MODES,
            history_prefix_seed=CLICKHOUSE_HISTORY_PREFIX_SEED_SUPPORTED,
            stable_logical_bindings=CLICKHOUSE_STABLE_LOGICAL_BINDINGS_SUPPORTED,
            per_relation_atomic_replace=CLICKHOUSE_PER_RELATION_ATOMIC_REPLACE,
            graph_atomic_publish=CLICKHOUSE_GRAPH_ATOMIC_PUBLISH,
            set_difference_comparison=CLICKHOUSE_SET_DIFFERENCE_COMPARISON_SUPPORTED,
            direct_rebuild=CLICKHOUSE_DIRECT_REBUILD_SUPPORTED,
        )

    def load_catalog(self, database: str) -> CatalogSnapshot:
        """Load a neutral catalog snapshot from ClickHouse system tables."""

        return load_clickhouse_catalog(
            connection=self,
            adapter_identity=self.adapter_identity,
            database=database,
        )

    def load_refresh_states(self, database: str) -> tuple[AdapterRefreshState, ...]:
        """Report ClickHouse refreshable view state so stale relations stay visible."""

        return load_clickhouse_refresh_states(connection=self, database=database)

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        """Return available ClickHouse columns for one framework metadata table."""

        result: AdapterQueryResult = self.query(
            f"SELECT name FROM system.columns WHERE database = '{database}' AND table = '{table}'"
        )
        return frozenset(str(row[0]) for row in result.rows)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        """Inspect ClickHouse stable bindings and deployment-specific tables."""

        return build_inspected_managed_table_state(client=self, database=database)

    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a ClickHouse query and normalize the returned rows."""

        return self._query(statement=statement, query_id=None)

    def execute_workflow_query(self, *, statement: str, query_id: str | None) -> AdapterQueryResult:
        """Execute a workflow query with a ClickHouse query ID."""

        return self._query(statement=statement, query_id=query_id)

    def _query(self, *, statement: str, query_id: str | None) -> AdapterQueryResult:
        settings: dict[str, str] | None = (
            None if query_id is None else {_QUERY_ID_SETTING: query_id}
        )

        try:
            raw_result: RawClickHouseQueryResult = (
                self._raw_client.query(query=statement)
                if settings is None
                else self._raw_client.query(query=statement, settings=settings)
            )
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
        result_rows: Sequence[Sequence[object]] = raw_result.result_rows
        return AdapterQueryResult(
            column_names=tuple(raw_result.column_names),
            rows=tuple(tuple(row) for row in result_rows),
        )

    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        """Execute exact workflow SQL and preserve ClickHouse mutation evidence."""

        return self._execute_workflow_sql(statement=statement, query_id=None)

    def execute_workflow_mutation(
        self, *, statement: str, query_id: str | None
    ) -> AdapterMutationResult:
        """Execute workflow SQL with a ClickHouse query ID."""

        return self._execute_workflow_sql(statement=statement, query_id=query_id)

    def _execute_workflow_sql(
        self, *, statement: str, query_id: str | None
    ) -> AdapterMutationResult:
        settings: dict[str, str] | None = (
            None if query_id is None else {_QUERY_ID_SETTING: query_id}
        )

        try:
            summary: object = (
                self._raw_client.command(cmd=statement)
                if settings is None
                else self._raw_client.command(cmd=statement, settings=settings)
            )
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
        if (
            not isinstance(summary, QuerySummary)
            or CLICKHOUSE_WRITTEN_ROWS_SUMMARY_KEY not in summary.summary
        ):
            return AdapterMutationResult()
        return AdapterMutationResult(written_rows=summary.written_rows)

    def load_statement_progress(self, *, query_id: str) -> AdapterStatementProgress | None:
        """Read one active query snapshot from ClickHouse system.processes."""

        query_id_literal: str = query_id.replace("\\", "\\\\").replace("'", "\\'")
        result: AdapterQueryResult = self.query(
            "SELECT elapsed, read_rows, read_bytes, total_rows_approx, memory_usage, "
            "Settings AS settings FROM system.processes "
            f"WHERE query_id = '{query_id_literal}' LIMIT 1"
        )
        rows: tuple[Mapping[str, object], ...] = result.named_rows()
        if not rows:
            return None
        row: Mapping[str, object] = rows[0]
        raw_settings: object = row["settings"]
        settings: tuple[tuple[str, str], ...] = (
            tuple(sorted((str(name), str(value)) for name, value in raw_settings.items()))
            if isinstance(raw_settings, Mapping)
            else ()
        )
        return AdapterStatementProgress(
            elapsed_seconds=float(str(row["elapsed"])),
            read_rows=int(str(row["read_rows"])),
            read_bytes=int(str(row["read_bytes"])),
            total_rows_approx=int(str(row["total_rows_approx"])),
            memory_usage_bytes=int(str(row["memory_usage"])),
            settings=settings,
        )

    def capture_warehouse_timestamp(self) -> str:
        """Capture ClickHouse server time as an exact UTC DateTime64(3) string."""

        result: AdapterQueryResult = self.query(
            "SELECT toString(now64(3, 'UTC'), 'UTC') AS warehouse_timestamp"
        )
        if not result.rows:
            raise AdapterResultError("ClickHouse returned no warehouse timestamp")
        return str(result.rows[0][0])

    def render_ensure_database(self, database: str) -> str:
        """Render exact ClickHouse database creation SQL."""

        return render_clickhouse_ensure_database(database)

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
        """Render one neutral resource request as ClickHouse SQL."""

        return render_clickhouse_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        """Render the exact idempotent ClickHouse metadata migration."""

        self.validate_metadata_state(database)
        return render_clickhouse_metadata_migration_workflow(database)

    def render_persist_metadata_state(
        self, *, database: str, state: AdapterMetadataState
    ) -> tuple[str, ...]:
        """Render exact ClickHouse metadata persistence SQL."""

        self.validate_metadata_state(database)
        return render_clickhouse_metadata_state(database=database, state=state)

    def render_terminal_observations(
        self,
        *,
        database: str,
        invocation: AdapterInvocationRecord,
        node_results: tuple[AdapterNodeResultRecord, ...],
    ) -> tuple[str, ...]:
        """Render terminal UI observations without exposing them to lifecycle readers."""

        self.validate_metadata_state(database)
        state: AdapterMetadataState = AdapterMetadataState(
            object_states=(),
            deployments=(),
            deployment_watermarks=(),
            publish_events=(),
            invocations=(invocation,),
            node_results=node_results,
        )
        return (
            *render_clickhouse_metadata_migration_workflow(database),
            *render_clickhouse_metadata_state(database=database, state=state),
        )

    def render_latest_node_status_query(
        self,
        *,
        database: str,
        project_identity: str,
        target_identity: str,
        nodes: tuple[AdapterCurrentQualityNode, ...],
    ) -> str:
        """Render current, stale, and never-run Quality UI states."""

        self.validate_metadata_state(database)
        return render_clickhouse_latest_node_status_query(
            database=database,
            project_identity=project_identity,
            target_identity=target_identity,
            nodes=nodes,
        )

    def validate_metadata_state(self, database: str) -> None:
        """Reject the intentionally incompatible pre-0.11 quality result schema."""

        columns: frozenset[str] = self.metadata_columns(
            database=database,
            table=METADATA_NODE_RESULTS_TABLE_NAME,
        )
        if not columns or _NODE_RESULT_REQUIRED_COLUMNS <= columns:
            return
        raise AdapterWarehouseError(
            f"{database}.{METADATA_NODE_RESULTS_TABLE_NAME} uses an incompatible pre-0.11 "
            "schema; drop this pre-production metadata table and retry so StreamBuild can "
            "recreate it"
        )

    def render_run_events(
        self,
        *,
        database: str,
        events: tuple[AdapterRunEventRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render incremental run-event inserts for the live run timeline."""

        return render_clickhouse_run_event_inserts(
            database=database, events=events, include_migration=include_migration
        )

    def render_run_statements(
        self,
        *,
        database: str,
        statements: tuple[AdapterRunStatementRecord, ...],
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render the durable SQL statement set for one run."""

        return render_clickhouse_run_statement_inserts(
            database=database,
            statements=statements,
            include_migration=include_migration,
        )

    def render_sensor_state(
        self,
        *,
        database: str,
        state: AdapterSensorState,
        include_migration: bool = False,
    ) -> tuple[str, ...]:
        """Render incremental sensor-state inserts for durable automation."""

        return render_clickhouse_sensor_state_inserts(
            database=database, state=state, include_migration=include_migration
        )

    def render_sensor_retention_cleanup(
        self, *, database: str, retention_days: int
    ) -> tuple[str, ...]:
        """Render bounded ClickHouse deletes for aged sensor ticks and steps."""

        return render_clickhouse_sensor_retention_cleanup(
            database=database, retention_days=retention_days
        )

    def load_direct_fingerprints(
        self, *, database: str, logical_model_identities: tuple[str, ...]
    ) -> AdapterDirectFingerprintSnapshot:
        """Load optional logical SQL baselines from ClickHouse metadata."""

        return load_clickhouse_direct_fingerprints(
            connection=self,
            database=database,
            logical_model_identities=logical_model_identities,
        )

    def render_direct_fingerprint_observations(
        self,
        *,
        database: str,
        fingerprints: tuple[AdapterDirectFingerprintRecord, ...],
    ) -> tuple[str, ...]:
        """Render terminal best-effort logical direct SQL baselines."""

        return render_clickhouse_direct_fingerprint_observations(
            database=database,
            fingerprints=fingerprints,
        )

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        """Load persisted ClickHouse deployments and publish events."""

        return load_clickhouse_deployment_inventory(connection=self, database=database)

    def render_replay_coverage_query(self, request: AdapterReplayCoverageRequest) -> str:
        """Render retained coverage selected by the replay window."""

        return render_clickhouse_replay_coverage_query(request)

    def render_replay_from_capture(self, request: AdapterCapturedReplayRequest) -> str:
        """Render replay SQL from boundaries captured by this process."""

        return render_clickhouse_replay_from_capture(request)

    def render_replay_from_deployment(
        self, request: AdapterDeploymentReplayRequest
    ) -> tuple[str, ...]:
        """Render fixed-cardinality replay against deployment-stored cutoffs."""

        return render_clickhouse_replay_from_deployment(request)

    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        """Compare active and staged ClickHouse relations."""

        return compare_clickhouse_readiness(connection=self, request=request)

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        """Render exact ClickHouse stable binding SQL."""

        return render_clickhouse_stable_binding_replacement(connection=self, request=request)

    def render_cleanup_relations(self, request: AdapterRelationCleanupRequest) -> tuple[str, ...]:
        """Render guarded exact ClickHouse relation cleanup SQL."""

        return render_clickhouse_relation_cleanup(connection=self, request=request)

    def close(self) -> None:
        """Close the underlying ClickHouse connection."""

        try:
            self._raw_client.close()
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
