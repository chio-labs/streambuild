from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from textwrap import dedent

from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
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
from streambuild.executor.backfill.main._ensure_metadata_tables import ensure_metadata_tables
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
          order_by: ["order_id"]
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
          order_by: ["order_id"]
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
          order_by: ["order_id"]
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
          order_by: ["order_id"]
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
