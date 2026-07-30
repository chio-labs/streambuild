import json
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from textwrap import dedent
from typing import cast

from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterCapabilities,
    AdapterConnectionConfig,
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
from streambuild.adapters.clickhouse._helpers.inspection import load_clickhouse_catalog
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.backfill.main._run_backfill import run_backfill
from streambuild.cli.backfill.models import BackfillCommandOptions
from streambuild.cli.build._helpers.preview import build_direct_build_preview
from streambuild.cli.build.constants import STREAMBUILD_TOOL_VERSION
from streambuild.cli.build.main._run_build import run_build
from streambuild.cli.build.models import BuildCommandOptions, BuildPreviewContext
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.executor.backfill.main._ensure_metadata_tables import ensure_metadata_tables
from streambuild.executor.direct.main.execute_direct_build import execute_direct_build
from streambuild.executor.direct.models import (
    DirectBuildRequest,
    DirectBuildResult,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings

BACKFILL_PIPELINES_ROOT: Path = Path("tests/fixtures/basic_project/pipelines")
SELECTOR_PIPELINES_ROOT: Path = Path("tests/fixtures/selector_project/pipelines")


def write_managed_source_project(
    *, project_dir: Path, replay_boundary_mode: str = "offsets"
) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.toml").write_text(
        'name = "integration_project"\ndefault_target = "test"\n\n'
        "[settings]\nvirtual_environments = true\n\n"
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    source_dir: Path = project_dir / "sources"
    source_dir.mkdir()
    (source_dir / "orders.yml").write_text(
        "sources:\n"
        "  - name: orders\n"
        "    kind: kafka\n"
        "    broker_list: kafka:9092\n"
        "    topic: source.orders\n"
        "    replay_boundary:\n"
        f"      mode: {replay_boundary_mode}\n",
        encoding="utf-8",
    )


class RecordingDelegatingConnection(AdapterConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        self._delegate: AdapterConnection = delegate
        self.catalog_load_count: int = 0
        self.query_statements: list[str] = []

    @property
    def adapter_identity(self) -> AdapterIdentity:
        return self._delegate.adapter_identity

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._delegate.capabilities

    def load_catalog(self, database: str) -> CatalogSnapshot:
        self.catalog_load_count += 1
        return load_clickhouse_catalog(
            connection=self,
            adapter_identity=self.adapter_identity,
            database=database,
        )

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        return self._delegate.metadata_columns(database=database, table=table)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        return self._delegate.inspect_managed_table_state(database)

    def load_target_ownership(self, database: str) -> tuple[AdapterOwnershipRecord, ...]:
        return self._delegate.load_target_ownership(database)

    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        self._delegate.record_target_ownership(database=database, records=records)

    def command(self, statement: str) -> None:
        self._delegate.command(statement)

    def query(self, statement: str) -> AdapterQueryResult:
        self.query_statements.append(statement)
        return self._delegate.query(statement)

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        self._delegate.insert_rows(table=table, rows=rows)

    def ensure_database(self, database: str) -> None:
        self._delegate.ensure_database(database)

    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        return self._delegate.render_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        self._delegate.realize_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def migrate_metadata_state(self, database: str) -> None:
        self._delegate.migrate_metadata_state(database)

    def persist_metadata_state(self, *, database: str, state: AdapterMetadataState) -> None:
        self._delegate.persist_metadata_state(database=database, state=state)

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        return self._delegate.load_deployment_inventory(database)

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        self._delegate.execute_replay(request)

    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        return self._delegate.compare_readiness(request)

    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        return self._delegate.replace_stable_bindings(request)

    def cleanup_relations(
        self, request: AdapterRelationCleanupRequest
    ) -> AdapterRelationCleanupResult:
        return self._delegate.cleanup_relations(request)

    def close(self) -> None:
        self._delegate.close()


class FailOnceRealizationConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._realization_actions: Iterator[Callable[..., None]] = iter(
            (
                self._reject_realization,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
            )
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        next(self._realization_actions)(
            resource=resource, database=database, if_not_exists=if_not_exists
        )

    def _reject_realization(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        del resource, database, if_not_exists
        raise AdapterWarehouseError("injected failure after direct teardown")


class FailOnceReplayConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._replay_actions: Iterator[Callable[[AdapterReplayRequest], None]] = iter(
            (self._reject_replay, self._delegate.execute_replay)
        )

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        next(self._replay_actions)(request)

    def _reject_replay(self, request: AdapterReplayRequest) -> None:
        del request
        raise AdapterWarehouseError("injected failure after direct relations became live")


class FailSecondReplayOnceConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self.replay_targets: list[str] = []
        self._replay_actions: Iterator[Callable[[AdapterReplayRequest], None]] = iter(
            (
                self._delegate.execute_replay,
                self._reject_replay,
                self._delegate.execute_replay,
                self._delegate.execute_replay,
                self._delegate.execute_replay,
            )
        )

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        self.replay_targets.append(request.relations.target)
        next(self._replay_actions)(request)

    def _reject_replay(self, request: AdapterReplayRequest) -> None:
        del request
        raise AdapterWarehouseError("injected failure during second population segment")


class FailOnceDropConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._command_actions: Iterator[Callable[[str], None]] = iter(
            (
                self._reject_command,
                self._delegate.command,
                self._delegate.command,
                self._delegate.command,
                self._delegate.command,
                self._delegate.command,
                self._delegate.command,
            )
        )

    def command(self, statement: str) -> None:
        next(self._command_actions)(statement)

    def _reject_command(self, statement: str) -> None:
        del statement
        raise AdapterWarehouseError("injected failure during selected teardown")


class FailOnceViewRealizationConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._realization_actions: Iterator[Callable[..., None]] = iter(
            (
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._reject_realization,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
                self._delegate.realize_resource,
            )
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        next(self._realization_actions)(
            resource=resource, database=database, if_not_exists=if_not_exists
        )

    def _reject_realization(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        del resource, database, if_not_exists
        raise AdapterWarehouseError("injected failure during selected view attachment")


class FailOnceBoundaryQueryConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._query_actions: Iterator[Callable[[str], AdapterQueryResult]] = iter(
            (
                self._delegate.query,
                self._delegate.query,
                self._delegate.query,
                self._delegate.query,
                self._reject_query,
                *([self._delegate.query] * 16),
            )
        )

    def load_catalog(self, database: str) -> CatalogSnapshot:
        return self._delegate.load_catalog(database)

    def query(self, statement: str) -> AdapterQueryResult:
        return next(self._query_actions)(statement)

    def _reject_query(self, statement: str) -> AdapterQueryResult:
        del statement
        raise AdapterWarehouseError("injected failure during selected boundary capture")


class FailFinalOwnershipOnceConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self._ownership_actions: Iterator[Callable[..., None]] = iter(
            (
                self._delegate.record_target_ownership,
                self._reject_ownership,
                self._delegate.record_target_ownership,
                self._delegate.record_target_ownership,
            )
        )

    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        next(self._ownership_actions)(database=database, records=records)

    def _reject_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        del database, records
        raise AdapterWarehouseError("injected failure during final ownership persistence")


class DirectActionRecordingConnection(RecordingDelegatingConnection):
    def __init__(self, delegate: AdapterConnection) -> None:
        super().__init__(delegate)
        self.command_statements: list[str] = []
        self.realized_relation_names: list[str] = []
        self.replay_targets: list[str] = []
        self.replay_requests: list[AdapterReplayRequest] = []

    def command(self, statement: str) -> None:
        self.command_statements.append(statement)
        super().command(statement)

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        self.realized_relation_names.append(resource.name)
        super().realize_resource(resource=resource, database=database, if_not_exists=if_not_exists)

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        self.replay_targets.append(request.relations.target)
        self.replay_requests.append(request)
        super().execute_replay(request)


class AdoptedLiveInsertConnection(DirectActionRecordingConnection):
    def __init__(self, delegate: AdapterConnection, *, database: str, values_sql: str) -> None:
        super().__init__(delegate)
        self._database: str = database
        self._values_sql: str = values_sql
        self._post_realization_actions: Iterator[Callable[[], None]] = iter(
            (self._do_nothing, self._insert_live_rows)
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        super().realize_resource(resource=resource, database=database, if_not_exists=if_not_exists)
        next(self._post_realization_actions)()

    def _do_nothing(self) -> None:
        return None

    def _insert_live_rows(self) -> None:
        self._delegate.command(
            f"INSERT INTO {self._database}.orders_existing VALUES {self._values_sql}"
        )


class ManagedLiveInsertConnection(DirectActionRecordingConnection):
    def __init__(
        self,
        delegate: AdapterConnection,
        *,
        database: str,
        rows: tuple[tuple[str, int, int], ...],
    ) -> None:
        super().__init__(delegate)
        self._database: str = database
        self._rows: tuple[tuple[str, int, int], ...] = rows
        self._post_realization_actions: Iterator[Callable[[], None]] = iter(
            (self._do_nothing, self._insert_live_rows)
        )

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        super().realize_resource(resource=resource, database=database, if_not_exists=if_not_exists)
        next(self._post_realization_actions)()

    def _do_nothing(self) -> None:
        return None

    def _insert_live_rows(self) -> None:
        insert_landing_rows(
            connection=self._delegate,
            database=self._database,
            rows=self._rows,
        )


def build_managed_clickhouse_client(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    *,
    database: str,
) -> AdapterConnection:
    return ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=database,
        )
    )


def build_deployment_status_query(database: str) -> str:
    return (
        "SELECT name FROM system.tables "
        f"WHERE database = '{database}' AND name = 'streambuild_deployments'"
    )


def build_runtime_details_table_query(database: str) -> str:
    return (
        "SELECT name FROM system.tables "
        f"WHERE database = '{database}' AND name = 'streambuild_deployment_runtime_details'"
    )


def write_source_mode_plan_project(
    *, project_dir: Path, source_contents: str, model_contents: str
) -> Path:
    """Write one registry-backed plan project for a managed or adopted source mode."""

    pipelines_root: Path = project_dir / "pipelines"
    pipeline_dir: Path = pipelines_root / "orders"
    pipeline_dir.mkdir(parents=True)
    (project_dir / "streambuild_project.toml").write_text(
        'name = "source_mode_project"\ndefault_target = "test"\n\n'
        "[settings]\nvirtual_environments = true\n\n"
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    source_dir: Path = project_dir / "sources"
    source_dir.mkdir()
    (source_dir / "orders.yml").write_text(
        dedent(source_contents).strip() + "\n",
        encoding="utf-8",
    )
    (pipeline_dir / "pipeline.yml").write_text(
        "source: orders\n",
        encoding="utf-8",
    )
    (pipeline_dir / "orders_enriched.sql").write_text(
        dedent(model_contents).strip() + "\n",
        encoding="utf-8",
    )
    return pipelines_root


def write_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_managed_source_project(project_dir=project_dir)
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        "source: orders",
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "negative_line_totals.sql",
        """
        AUDIT (
          severity: "warning",
          description: "Line totals should not be negative",
        );

        SELECT order_id, line_total
        FROM __ref("order_items")
        WHERE line_total < 0
        """,
    )


def write_backfill_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_managed_source_project(project_dir=project_dir, replay_boundary_mode="timestamp")
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        "source: orders",
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "orders_enriched.sql",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(kafka_key AS String) AS order_id,
          CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "known_order_id.sql",
        """
        AUDIT (
          description: "ord_001 should be flagged by the staged quality check",
        );

        SELECT order_id
        FROM __ref("orders_enriched")
        WHERE order_id = 'ord_001'
        """,
    )


def write_generic_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
        write_schema_yaml_file,
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_managed_source_project(project_dir=project_dir)
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        "source: orders",
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "generic" / "not_null.sql",
        """
        AUDIT ();

        SELECT @column
        FROM __ref("@model")
        WHERE @column IS NULL
        """,
    )
    write_schema_yaml_file(
        project_dir / "pipelines" / "order_events" / "schema.yml",
        """
        models:
          - name: order_items
            columns:
              - name: order_id
                audits:
                  - not_null:
                      name: order items order id not null
                      severity: warning
        """,
    )


def write_multi_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_managed_source_project(project_dir=project_dir)
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        "source: orders",
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "quality.sql",
        """
        AUDIT (
          name: "negative line totals",
          severity: "warning",
        );

        SELECT order_id, line_total
        FROM __ref("order_items")
        WHERE line_total < 0;

        AUDIT (
          name: "missing order ids",
          severity: "warning",
        );

        SELECT order_id
        FROM __ref("order_items")
        WHERE order_id = 'ord_missing'
        """,
    )


AUDIT_PROJECT_WRITER_BY_NAME: Mapping[str, Callable[[Path], None]] = {
    "singular": write_audit_project_files,
    "generic": write_generic_audit_project_files,
    "multi": write_multi_audit_project_files,
}

NULLABLE_ORDER_ITEMS_COLUMNS: str = "order_id Nullable(String), line_total Nullable(Float64)"
KEYED_ORDER_ITEMS_COLUMNS: str = "order_id String, line_total Nullable(Float64)"
UNORDERED_ORDER_ITEMS_ORDER_BY: str = "tuple()"
KEYED_ORDER_ITEMS_ORDER_BY: str = "(order_id)"


def write_audit_project_for(*, project_writer_name: str, project_dir: Path) -> None:
    """Write the audit project fixture selected by a test case."""

    AUDIT_PROJECT_WRITER_BY_NAME[project_writer_name](project_dir)


def build_order_items_ddl(*, database: str, columns: str, order_by: str) -> str:
    """Build the order-items table DDL a live audit test case expects."""

    return (
        f"CREATE TABLE {database}.tbl__order_items ({columns}) "
        f"ENGINE = MergeTree() ORDER BY {order_by}"
    )


def ensure_backfill_metadata_tables(*, managed_client: AdapterConnection, database: str) -> None:
    """Create the metadata tables so absent rows mean no deployment was recorded."""

    ensure_metadata_tables(client=managed_client, metadata_database=database)


def load_deployment_status_rows(
    *, clickhouse_client: Client, database: str
) -> tuple[tuple[str, ...], ...]:
    """Load recorded deployment statuses in deployment order."""

    query: str = f"SELECT status FROM {database}.streambuild_deployments ORDER BY deployment_id"
    return tuple(_stringify_row(row) for row in clickhouse_client.query(query).result_rows)


def _stringify_row(row: Sequence[object]) -> tuple[str, ...]:
    return tuple(str(value) for value in row)


def load_selected_root_names(*, clickhouse_client: Client, database: str) -> tuple[str, ...]:
    """Load the selected root names recorded against every deployment."""

    query: str = (
        "SELECT JSONExtractString(root_key, 'name') FROM "
        f"{database}.streambuild_deployments "
        "ARRAY JOIN JSONExtractArrayRaw(selected_root_keys_json) AS root_key "
        "ORDER BY JSONExtractString(root_key, 'name')"
    )
    return tuple(str(row[0]) for row in clickhouse_client.query(query).result_rows)


def load_runtime_execution_modes(
    *, clickhouse_client: Client, database: str
) -> tuple[tuple[str, str | None], ...]:
    """Load the recorded execution mode per root object."""

    query: str = (
        "SELECT root_object_name, execution_mode "
        f"FROM {database}.streambuild_deployment_runtime_details "
        "ORDER BY root_object_name"
    )
    return tuple((str(row[0]), row[1]) for row in clickhouse_client.query(query).result_rows)


SINGLE_EXPECTED_SQL_TEST: str = """
    TEST ();

    WITH
    helper_orders AS (
      SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
    ),
    __source__orders AS (
      SELECT * FROM helper_orders
    ),
    expected_rows AS (
      SELECT 'ord_001' AS order_id, {expected_line_total} AS line_total
    ),
    __expected__order_items AS (
      SELECT * FROM expected_rows
    )
    SELECT 1
    """

MULTI_NAMED_SQL_TESTS: str = """
    TEST (name: "line total computes correctly");

    WITH
    helper_orders AS (
      SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
    ),
    __source__orders AS (
      SELECT * FROM helper_orders
    ),
    __expected__order_items AS (
      SELECT 'ord_001' AS order_id, 20.0 AS line_total
    )
    SELECT 1;

    TEST (name: "line total remains stable on repeat");

    WITH
    helper_orders AS (
      SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
    ),
    __source__orders AS (
      SELECT * FROM helper_orders
    ),
    __expected__order_items AS (
      SELECT 'ord_001' AS order_id, 20.0 AS line_total
    )
    SELECT 1
    """

MULTI_TARGET_FAILING_SQL_TEST: str = """
    TEST ();

    WITH
    helper_orders AS (
      SELECT 'ord_001' AS order_id, 2 AS quantity, 10.0 AS unit_price
    ),
    __source__orders AS (
      SELECT * FROM helper_orders
    ),
    __expected__order_items AS (
      SELECT 'ord_001' AS order_id, 25.0 AS line_total
    ),
    __expected__daily_revenue AS (
      SELECT 'ord_001' AS order_id, 30.0 AS line_total
    )
    SELECT 1
    """

DOWNSTREAM_REF_SQL_TEST: str = """
    TEST ();

    WITH
    __ref__order_items AS (
      SELECT 'ord_001' AS order_id, 20.0 AS line_total
    ),
    __expected__daily_revenue AS (
      SELECT 'ord_001' AS order_id, 20.0 AS line_total
    )
    SELECT 1
    """


SEMANTICS_MODEL_SQL_BY_NAME: tuple[tuple[str, str], ...] = (
    (
        "order_items",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __source("orders")
        """,
    ),
    (
        "daily_revenue",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS line_total
        FROM __ref("order_items")
        """,
    ),
    (
        "revenue_report",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS reported_total
        FROM __ref("daily_revenue")
        """,
    ),
    (
        "order_tax",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total * 0.1 AS Nullable(Float64)) AS tax_total
        FROM __ref("order_items")
        """,
    ),
    (
        "order_summary",
        """
        MODEL (
          order_by ["order_id"]
        );

        SELECT
          CAST(daily.order_id AS String) AS order_id,
          CAST(daily.line_total + tax.tax_total AS Nullable(Float64)) AS total_with_tax
        FROM __ref("daily_revenue") AS daily
        JOIN __ref("order_tax", ref_type='reference') AS tax ON daily.order_id = tax.order_id
        """,
    ),
)


def write_sql_test_semantics_project(
    *, project_dir: Path, sql_test_content: str, macro_file_contents: str
) -> None:
    """Write one three-model project used to prove SQL-test comparison semantics."""

    write_managed_source_project(project_dir=project_dir)
    pipeline_dir: Path = project_dir / "pipelines" / "order_events"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "pipeline.yml").write_text("source: orders\n", encoding="utf-8")
    model_name: str
    model_sql: str
    for model_name, model_sql in SEMANTICS_MODEL_SQL_BY_NAME:
        (pipeline_dir / f"{model_name}.sql").write_text(
            dedent(model_sql).strip() + "\n", encoding="utf-8"
        )
    test_file_path: Path = project_dir / "tests" / "order_events" / "test_semantics.sql"
    test_file_path.parent.mkdir(parents=True, exist_ok=True)
    test_file_path.write_text(dedent(sql_test_content).strip() + "\n", encoding="utf-8")
    macro_dir: Path = project_dir / "macros"
    macro_dir.mkdir(parents=True, exist_ok=True)
    (macro_dir / "helpers.py").write_text(
        dedent(macro_file_contents).strip() + "\n", encoding="utf-8"
    )


DIRECT_SCOPE_PREREQUISITE_RELATIONS: tuple[str, ...] = ("raw__orders",)
DIRECT_SCOPE_MODEL_RELATIONS: tuple[str, ...] = (
    "tbl__alpha",
    "mv__alpha",
    "tbl__beta",
    "mv__beta",
    "tbl__gamma",
    "mv__gamma",
    "tbl__delta",
    "mv__delta",
)
_OWNERSHIP_ROW_NAMES_BY_FLAG: dict[bool, tuple[str, ...]] = {
    False: (),
    True: DIRECT_SCOPE_MODEL_RELATIONS,
}
_RELATION_NAMES_BY_FLAG: dict[bool, tuple[str, ...]] = {
    False: DIRECT_SCOPE_PREREQUISITE_RELATIONS,
    True: (*DIRECT_SCOPE_PREREQUISITE_RELATIONS, *DIRECT_SCOPE_MODEL_RELATIONS),
}


def settle_direct_scope_warehouse(
    *, connection: AdapterConnection, database: str, record_ownership: bool
) -> None:
    """Create the scope project's warehouse relations and optional direct ownership rows."""

    connection.ensure_database(database)
    connection.migrate_metadata_state(database)
    relation_name: str
    for relation_name in _RELATION_NAMES_BY_FLAG[record_ownership]:
        connection.command(
            f"CREATE TABLE IF NOT EXISTS {database}.{relation_name} "
            "(order_id UInt64) ENGINE = MergeTree ORDER BY order_id"
        )
    ownership_relation_names: tuple[str, ...] = _OWNERSHIP_ROW_NAMES_BY_FLAG[record_ownership]
    ownership_rows: tuple[dict[str, object], ...] = tuple(
        cast(
            dict[str, object],
            {
                "database_name": database,
                "relation_name": relation_name,
                "resource_kind": "table",
                "logical_model_database": "",
                "logical_model_name": relation_name.split("__")[-1],
                "owning_mode": "direct",
                "tool_version": "integration",
            },
        )
        for relation_name in ownership_relation_names
    )
    connection.insert_rows(
        table=f"{database}.streambuild_target_ownership",
        rows=ownership_rows,
    )


def run_direct_plan(*, project_root: Path, database: str, connection: AdapterConnection) -> int:
    """Run `stb plan` in direct mode against a live warehouse connection."""

    return run_plan(
        pipelines_root=project_root / "pipelines",
        database=database,
        selectors=(),
        full_refresh=False,
        start_time=None,
        json_output=True,
        verbose=False,
        client=connection,
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def plan_scope_names(*, plan_json: str) -> tuple[str, ...]:
    """Return the execution scope model names reported by one direct plan."""

    payload: dict[str, object] = json.loads(plan_json)
    return tuple(cast(list[str], payload["execution_scope"]))


def plan_replay_root_models(*, plan_json: str) -> tuple[str, ...]:
    """Return the replay root model names reported by one direct plan."""

    payload: dict[str, object] = json.loads(plan_json)
    roots: list[dict[str, object]] = cast(list[dict[str, object]], payload["replay_roots"])
    return tuple(str(root["model"]) for root in roots)


def plan_relation_operations(*, plan_json: str) -> tuple[tuple[str, str], ...]:
    """Return every teardown and creation operation reported by one direct plan."""

    payload: dict[str, object] = json.loads(plan_json)
    operations: list[dict[str, object]] = [
        *cast(list[dict[str, object]], payload["teardown"]),
        *cast(list[dict[str, object]], payload["creation"]),
    ]
    return tuple((str(operation["action"]), str(operation["relation"])) for operation in operations)


def plan_ownership_labels(*, plan_json: str) -> tuple[str, ...]:
    """Return the distinct ownership labels reported across every plan entry."""

    payload: dict[str, object] = json.loads(plan_json)
    entries: list[dict[str, object]] = cast(list[dict[str, object]], payload["entries"])
    labels: set[str] = set()
    entry: dict[str, object]
    for entry in entries:
        classifications: list[dict[str, str]] = cast(list[dict[str, str]], entry["ownership"])
        labels.update(classification["ownership"] for classification in classifications)
    return tuple(sorted(labels))


DIRECT_BUILD_MODEL_SQL: str = (
    "SELECT\n"
    "  kafka_key::String AS order_id,\n"
    "  _replay_partition::Int32 AS _replay_partition,\n"
    "  _replay_offset::Int64 AS _replay_offset\n"
    'FROM __source("orders")'
)
DIRECT_BUILD_MODEL_NAME: str = "orders_enriched"
DIRECT_BUILD_TARGET_TABLE_NAME: str = "tbl__orders_enriched"
DIRECT_BUILD_LANDING_TABLE_NAME: str = "raw__orders"
_DIRECT_BUILD_SOURCE_YML: str = (
    "sources:\n"
    "  - name: orders\n"
    "    kind: kafka\n"
    "    broker_list: {broker_list}\n"
    "    topic: {topic}\n"
    "    replay_boundary: {{mode: offsets}}\n"
)
_DIRECT_BUILD_SETTINGS_BY_MODE: dict[bool, str] = {
    False: "",
    True: "\n[settings]\nvirtual_environments = true\n",
}
_DIRECT_SELECTED_GRAPH_SQL_BY_NAME: tuple[tuple[str, str], ...] = (
    (
        "alpha",
        "SELECT kafka_key::String AS order_id, "
        "_replay_partition::Int32 AS _replay_partition, "
        "_replay_offset::Int64 AS _replay_offset "
        'FROM __source("orders")',
    ),
    (
        "beta",
        "SELECT order_id::String AS order_id, "
        "_replay_partition::Int32 AS _replay_partition, "
        "_replay_offset::Int64 AS _replay_offset "
        'FROM __ref("alpha")',
    ),
    (
        "gamma",
        "SELECT order_id::String AS order_id, "
        "concat(order_id, '-gamma')::String AS gamma_marker, "
        "_replay_partition::Int32 AS _replay_partition, "
        "_replay_offset::Int64 AS _replay_offset "
        'FROM __ref("beta")',
    ),
    (
        "delta",
        "SELECT a.order_id::String AS order_id, g.gamma_marker::String AS gamma_marker, "
        "a._replay_partition::Int32 AS _replay_partition, "
        "a._replay_offset::Int64 AS _replay_offset "
        'FROM __ref("alpha") AS a INNER JOIN '
        '__ref("gamma", ref_type="reference") AS g ON a.order_id = g.order_id',
    ),
)


def write_direct_build_project(
    *,
    project_root: Path,
    topic: str = "source.orders",
    broker_list: str = "kafka:9092",
    audit_sql_by_name: tuple[tuple[str, str], ...] = (),
    virtual_environments: bool = False,
) -> None:
    """Write a managed Kafka direct-mode project with one offsets-lineage model."""

    pipeline_root: Path = project_root / "pipelines" / "orders"
    source_root: Path = project_root / "sources"
    audit_root: Path = project_root / "audits"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    (project_root / "streambuild_project.toml").write_text(
        'name = "direct_build"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n'
        f"{_DIRECT_BUILD_SETTINGS_BY_MODE[virtual_environments]}",
        encoding="utf-8",
    )
    (source_root / "orders.yml").write_text(
        _DIRECT_BUILD_SOURCE_YML.format(broker_list=broker_list, topic=topic),
        encoding="utf-8",
    )
    (pipeline_root / "pipeline.yml").write_text("source: orders\n", encoding="utf-8")
    (pipeline_root / f"{DIRECT_BUILD_MODEL_NAME}.sql").write_text(
        f'MODEL (order_by ["order_id"]);\n{DIRECT_BUILD_MODEL_SQL}\n',
        encoding="utf-8",
    )
    audit_name: str
    audit_sql: str
    for audit_name, audit_sql in audit_sql_by_name:
        (audit_root / audit_name).write_text(audit_sql, encoding="utf-8")


def write_direct_selected_graph_project(*, project_root: Path) -> None:
    """Write the selected-rebuild fan-in graph with replay lineage on every model."""

    pipeline_root: Path = project_root / "pipelines" / "orders"
    source_root: Path = project_root / "sources"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    (project_root / "streambuild_project.toml").write_text(
        'name = "direct_selected_graph"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    (source_root / "orders.yml").write_text(
        _DIRECT_BUILD_SOURCE_YML.format(broker_list="kafka:9092", topic="source.selected_orders"),
        encoding="utf-8",
    )
    (pipeline_root / "pipeline.yml").write_text("source: orders\n", encoding="utf-8")
    model_name: str
    model_sql: str
    for model_name, model_sql in _DIRECT_SELECTED_GRAPH_SQL_BY_NAME:
        (pipeline_root / f"{model_name}.sql").write_text(
            f'MODEL (order_by ["order_id"]);\n{model_sql}\n', encoding="utf-8"
        )


def write_direct_aggregate_project(*, project_root: Path) -> None:
    """Write an alpha-to-aggregate-beta direct rebuild project."""

    write_direct_selected_graph_project(project_root=project_root)
    pipeline_root: Path = project_root / "pipelines" / "orders"
    (pipeline_root / "gamma.sql").unlink()
    (pipeline_root / "delta.sql").unlink()
    (pipeline_root / "beta.sql").write_text(
        'MODEL (order_by ["order_id"]);\n'
        "SELECT order_id::String AS order_id, count()::UInt64 AS order_count "
        'FROM __ref("alpha") GROUP BY order_id\n',
        encoding="utf-8",
    )


def write_direct_selected_graph_audits(
    *, project_root: Path, audit_sql_by_name: tuple[tuple[str, str], ...]
) -> None:
    """Write discovered audits for the selected-rebuild graph."""

    audit_root: Path = project_root / "audits"
    audit_root.mkdir(exist_ok=True)
    audit_name: str
    audit_sql: str
    for audit_name, audit_sql in audit_sql_by_name:
        (audit_root / audit_name).write_text(audit_sql, encoding="utf-8")


def write_direct_adopted_source_project(
    *, project_root: Path, source_yml: str, model_sql: str
) -> None:
    """Write a direct project driven by one adopted source relation."""

    pipeline_root: Path = project_root / "pipelines" / "orders"
    source_root: Path = project_root / "sources"
    audit_root: Path = project_root / "audits"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    (project_root / "streambuild_project.toml").write_text(
        'name = "direct_adopted_source"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    (source_root / "orders.yml").write_text(source_yml, encoding="utf-8")
    (pipeline_root / "pipeline.yml").write_text("source: orders\n", encoding="utf-8")
    (pipeline_root / "orders_enriched.sql").write_text(model_sql, encoding="utf-8")
    (audit_root / "adopted_target.sql").write_text(
        'AUDIT (description: "adopted target is live");\n'
        "SELECT 'adopted-audit-marker' AS marker "
        'FROM __ref("orders_enriched") WHERE 0\n',
        encoding="utf-8",
    )


def run_direct_build(
    *,
    project_root: Path,
    database: str,
    connection: AdapterConnection,
    selectors: tuple[str, ...] = (),
    json_output: bool = True,
    auto_approve: bool = True,
) -> int:
    """Run `stb build` in direct mode against a live warehouse connection."""

    return run_build(
        options=BuildCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=database,
            metadata_database=database,
            selectors=selectors,
            json_output=json_output,
            verbose=False,
            auto_approve=auto_approve,
        ),
        client=connection,
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def insert_landing_rows(
    *,
    connection: AdapterConnection,
    database: str,
    rows: tuple[tuple[str, int, int], ...],
) -> None:
    """Insert replayable landing rows directly into the preserved raw relation."""

    values: str = ", ".join(
        f"('{order_key}', '', '', {partition_value}, {offset_value}, now64(3), "
        f"{partition_value}, {offset_value}, now64(3), '', now64(3), now64(3))"
        for order_key, partition_value, offset_value in rows
    )
    connection.command(
        f"INSERT INTO {database}.{DIRECT_BUILD_LANDING_TABLE_NAME} "
        "(kafka_key, kafka_value, kafka_topic, kafka_partition, kafka_offset, kafka_timestamp, "
        "_replay_partition, _replay_offset, _replay_timestamp, kafka_headers, kafka_landed_at, "
        f"_replay_landed_at) VALUES {values}"
    )


def insert_landing_rows_after_delay(
    *,
    connection_settings: ClickHouseConnectionSettings,
    database: str,
    rows: tuple[tuple[str, int, int], ...],
    delay_seconds: float,
) -> None:
    """Land rows on an independent connection while a build is stabilizing."""

    time.sleep(delay_seconds)
    connection: AdapterConnection = build_managed_clickhouse_client(
        connection_settings, database=database
    )
    try:
        insert_landing_rows(connection=connection, database=database, rows=rows)
    finally:
        connection.close()


def execute_direct_build_directly(
    *,
    project_root: Path,
    database: str,
    connection: AdapterConnection,
    stabilization_seconds: float,
    selectors: tuple[str, ...],
) -> DirectBuildResult:
    """Plan and execute one direct build with an explicit stabilization window."""

    preview: BuildPreviewContext = build_direct_build_preview(
        options=BuildCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=database,
            metadata_database=database,
            selectors=selectors,
            json_output=True,
            verbose=False,
            auto_approve=True,
        ),
        client=connection,
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
    return execute_direct_build(
        request=DirectBuildRequest(
            plan=preview.plan,
            realized_project=preview.analysis.realized_project,
            database=preview.database,
            metadata_database=preview.metadata_database,
            tool_version=STREAMBUILD_TOOL_VERSION,
            stabilization_seconds=stabilization_seconds,
        ),
        client=connection,
    )


def execute_warehouse_statements(
    *,
    connection: AdapterConnection,
    database: str,
    statements: tuple[str, ...],
) -> None:
    """Run explicit warehouse statements while arranging one integration scenario."""

    statement: str
    for statement in statements:
        connection.command(statement.format(database=database))


def run_virtual_environment_backfill(
    *,
    project_root: Path,
    database: str,
    connection: AdapterConnection,
) -> int:
    """Run `stb backfill` against a warehouse that direct mode may already own."""

    return run_backfill(
        options=BackfillCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=database,
            metadata_database=database,
            selectors=(),
            deployment_id=None,
            full_refresh=False,
            start_time=None,
            json_output=True,
            verbose=False,
            auto_approve=True,
        ),
        client=connection,
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def direct_build_order_ids(*, clickhouse_client: Client, database: str) -> tuple[str, ...]:
    """Return the order ids currently materialized in the direct build target."""

    rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {database}.{DIRECT_BUILD_TARGET_TABLE_NAME} ORDER BY order_id"
    ).result_rows
    return tuple(str(row[0]) for row in rows)


def warehouse_row_count(*, clickhouse_client: Client, database: str, statement: str) -> int:
    """Return one scalar count from a database-templated statement."""

    return int(clickhouse_client.query(statement.format(database=database)).result_rows[0][0])


def direct_owned_relation_names(*, connection: AdapterConnection, database: str) -> tuple[str, ...]:
    """Return every relation name durably claimed in the ownership table."""

    return tuple(
        sorted(record.relation_name for record in connection.load_target_ownership(database))
    )


def direct_owned_replay_coverage_ranges(
    *, connection: AdapterConnection, database: str
) -> tuple[tuple[str, str, str], ...]:
    """Return the table claim's persisted replay intervals in deterministic order."""

    record_by_name: dict[str, AdapterOwnershipRecord] = {
        record.relation_name: record for record in connection.load_target_ownership(database)
    }
    record: AdapterOwnershipRecord = record_by_name[DIRECT_BUILD_TARGET_TABLE_NAME]
    return tuple(
        (coverage.boundary_key, coverage.lower_value, coverage.upper_value)
        for coverage in record.replay_coverage
    )


def direct_graph_order_ids(
    *, clickhouse_client: Client, database: str, model_name: str
) -> tuple[str, ...]:
    """Return ordered identities from one selected-graph model target."""

    rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {database}.tbl__{model_name} ORDER BY order_id"
    ).result_rows
    return tuple(str(row[0]) for row in rows)


def direct_graph_delta_rows(
    *, clickhouse_client: Client, database: str
) -> tuple[tuple[str, str], ...]:
    """Return the fan-in target's identity and side-reference marker rows."""

    rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id, gamma_marker FROM {database}.tbl__delta ORDER BY order_id"
    ).result_rows
    return tuple((str(row[0]), str(row[1])) for row in rows)


def stringify_warehouse_rows(*, rows: Sequence[Sequence[object]]) -> tuple[tuple[str, ...], ...]:
    """Convert driver row values to deterministic strings."""

    converted: list[tuple[str, ...]] = []
    row: Sequence[object]
    for row in rows:
        converted.append(tuple(map(str, row)))
    return tuple(converted)
