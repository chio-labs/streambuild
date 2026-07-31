"""ClickHouse-backed implementation of the neutral connection contract."""

from __future__ import annotations

from collections.abc import Sequence

from clickhouse_connect.driver.exceptions import ClickHouseError, StreamFailureError

from streambuild.adapter.classes.adapter_connection import AdapterConnection
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
    AdapterView,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse._helpers.errors import translate_driver_error
from streambuild.adapters.clickhouse._helpers.inspection import load_clickhouse_catalog
from streambuild.adapters.clickhouse._helpers.lifecycle import (
    cleanup_clickhouse_relations,
    load_clickhouse_deployment_inventory,
    replace_clickhouse_stable_bindings,
)
from streambuild.adapters.clickhouse._helpers.managed_tables import (
    build_inspected_managed_table_state,
)
from streambuild.adapters.clickhouse._helpers.metadata import (
    load_clickhouse_target_ownership,
    migrate_clickhouse_metadata_state,
    persist_clickhouse_metadata_state,
    record_clickhouse_target_ownership,
    remove_clickhouse_target_ownership,
)
from streambuild.adapters.clickhouse._helpers.readiness import compare_clickhouse_readiness
from streambuild.adapters.clickhouse._helpers.rendering import render_clickhouse_resource
from streambuild.adapters.clickhouse._helpers.replay import execute_clickhouse_replay
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
)
from streambuild.adapters.clickhouse.types import (
    RawClickHouseClient,
    RawClickHouseQueryResult,
)


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

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        """Return available ClickHouse columns for one framework metadata table."""

        result: AdapterQueryResult = self.query(
            f"SELECT name FROM system.columns WHERE database = '{database}' AND table = '{table}'"
        )
        return frozenset(str(row[0]) for row in result.rows)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        """Inspect ClickHouse stable bindings and deployment-specific tables."""

        return build_inspected_managed_table_state(client=self, database=database)

    def load_target_ownership(self, database: str) -> tuple[AdapterOwnershipRecord, ...]:
        """Load durable StreamBuild ownership records for a ClickHouse database."""

        return load_clickhouse_target_ownership(connection=self, database=database)

    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        """Durably claim ClickHouse relations before they are created or replaced."""

        record_clickhouse_target_ownership(connection=self, database=database, records=records)

    def remove_target_ownership(
        self,
        *,
        database: str,
        target_database: str,
        relation_names: tuple[str, ...],
    ) -> None:
        """Remove retired ClickHouse ownership claims."""

        remove_clickhouse_target_ownership(
            connection=self,
            database=database,
            target_database=target_database,
            relation_names=relation_names,
        )

    def command(self, statement: str) -> None:
        """Execute a ClickHouse command statement."""

        try:
            self._raw_client.command(statement)
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error

    def query(self, statement: str) -> AdapterQueryResult:
        """Execute a ClickHouse query and normalize the returned rows."""

        try:
            raw_result: RawClickHouseQueryResult = self._raw_client.query(statement)
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
        result_rows: Sequence[Sequence[object]] = raw_result.result_rows
        return AdapterQueryResult(
            column_names=tuple(raw_result.column_names),
            rows=tuple(tuple(row) for row in result_rows),
        )

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        """Insert row mappings into a ClickHouse table."""

        if not rows:
            return

        column_names: tuple[str, ...] = tuple(rows[0].keys())
        row_values: list[list[object]] = []
        row: dict[str, object]
        for row in rows:
            row_values.append([row[column_name] for column_name in column_names])
        try:
            self._raw_client.insert(table=table, data=row_values, column_names=list(column_names))
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error

    def ensure_database(self, database: str) -> None:
        """Create a ClickHouse database when it does not already exist."""

        self.command(f"CREATE DATABASE IF NOT EXISTS {database}")

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

    def realize_resource(
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
    ) -> None:
        """Realize one neutral resource request in ClickHouse."""

        self.command(
            self.render_resource(
                resource=resource,
                database=database,
                if_not_exists=if_not_exists,
            )
        )

    def migrate_metadata_state(self, database: str) -> None:
        """Apply pending additive StreamBuild metadata migrations."""

        migrate_clickhouse_metadata_state(connection=self, database=database)

    def persist_metadata_state(self, *, database: str, state: AdapterMetadataState) -> None:
        """Persist adapter-neutral StreamBuild metadata in ClickHouse."""

        persist_clickhouse_metadata_state(connection=self, database=database, state=state)

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        """Load persisted ClickHouse deployments and publish events."""

        return load_clickhouse_deployment_inventory(connection=self, database=database)

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        """Seed and execute one replay request in ClickHouse."""

        execute_clickhouse_replay(connection=self, request=request)

    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        """Compare active and staged ClickHouse relations."""

        return compare_clickhouse_readiness(connection=self, request=request)

    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        """Replace ClickHouse stable views and report actual atomicity."""

        return replace_clickhouse_stable_bindings(connection=self, request=request)

    def cleanup_relations(
        self, request: AdapterRelationCleanupRequest
    ) -> AdapterRelationCleanupResult:
        """Drop requested ClickHouse relations synchronously."""

        return cleanup_clickhouse_relations(connection=self, request=request)

    def close(self) -> None:
        """Close the underlying ClickHouse connection."""

        try:
            self._raw_client.close()
        except (ClickHouseError, StreamFailureError) as error:
            raise translate_driver_error(error) from error
