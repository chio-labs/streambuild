from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterCapabilities,
    AdapterDeploymentInventory,
    AdapterIdentity,
    AdapterMutationResult,
    AdapterOwnershipRecord,
    AdapterQueryResult,
    AdapterReplayCoverageRange,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.plan_payload import build_replay_count_query
from streambuild.dev_server._helpers.state_queries import (
    build_extents_query,
    build_partitions_query,
    build_parts_query,
    build_relation_stats_query,
    build_throughput_query,
)
from streambuild.dev_server._helpers.static_assets import register_static_assets
from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
    write_project_configuration_and_source,
)

_ORDERS_CLEAN_MODEL: str = """
MODEL (
  description "Cleaned order rows.",
  order_by ["order_id", "_replay_partition", "_replay_offset"],
  columns (
    order_id (description "Primary order id", audits [not_null]),
  ),
);

SELECT
  CAST(order_id AS String) AS order_id,
  _replay_partition::Int64 AS _replay_partition,
  _replay_offset::Int64 AS _replay_offset
FROM __ref("orders")
"""

_NOT_NULL_GENERIC_AUDIT: str = """
AUDIT ();

SELECT @column
FROM __ref("@model")
WHERE @column IS NULL
"""


_ORDERS_SOURCE_WITH_FRESHNESS: str = """
sources:
  - name: orders
    kind: kafka
    broker_list: kafka:9092
    topic: source.orders
    replay_boundary:
      mode: offsets
    freshness:
      warn_after: 1h
      error_after: 4h
"""


def write_dev_server_project(*, project_dir: Path) -> None:
    write_project_configuration_and_source(project_dir=project_dir)
    write_pipeline_file(project_dir / "sources" / "orders.yml", _ORDERS_SOURCE_WITH_FRESHNESS)
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "orders_clean.sql",
        _ORDERS_CLEAN_MODEL,
    )
    write_pipeline_file(
        project_dir / "audits" / "generic" / "not_null.sql",
        _NOT_NULL_GENERIC_AUDIT,
    )


def build_compile_callable(*, project_dir: Path) -> Callable[[], CompileAnalysis]:
    def run_compile() -> CompileAnalysis:
        return analyze_project(
            pipelines_root=project_dir / "pipelines",
            loaded_project=load_project_input_for_path(path=project_dir),
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )

    return run_compile


def break_project_compile(*, project_dir: Path) -> None:
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "broken.sql",
        "SELECT 1 AS value",
    )


def build_test_client(*, project_dir: Path) -> TestClient:
    state: DevServerState = DevServerState(
        run_compile=build_compile_callable(project_dir=project_dir)
    )
    return TestClient(create_dev_app(state=state, project_dir=project_dir))


_STATIC_INDEX_CONTENTS: str = "<html>stb-dev-shell</html>"
_STATIC_APP_SCRIPT_CONTENTS: str = "console.log('stb-app-script');"
_STATIC_ROBOTS_CONTENTS: str = "User-agent: *"


def write_static_assets_build(*, assets_root: Path) -> None:
    (assets_root / "_app").mkdir(parents=True)
    (assets_root / "index.html").write_text(_STATIC_INDEX_CONTENTS)
    (assets_root / "_app" / "app.js").write_text(_STATIC_APP_SCRIPT_CONTENTS)
    (assets_root / "robots.txt").write_text(_STATIC_ROBOTS_CONTENTS)


def build_static_test_client(*, assets_root: Path) -> TestClient:
    app: FastAPI = register_static_assets(app=FastAPI(), assets_root=assets_root)
    return TestClient(app)


def named_payload_item(items: list, name: str) -> dict:
    by_name: dict = {item["name"]: item for item in items}
    return by_name[name]


def maybe_break_project_compile(*, project_dir: Path, break_compile: bool) -> None:
    writers: dict[bool, Callable[..., None]] = {
        True: break_project_compile,
        False: _skip_break,
    }
    writer: Callable[..., None] = writers[break_compile]
    writer(project_dir=project_dir)


def _skip_break(*, project_dir: Path) -> None:
    return None


class FakeAdapterConnection(AdapterConnection):
    """Exact-match canned warehouse: every expected query string maps to a result."""

    def __init__(
        self,
        *,
        catalog: CatalogSnapshot,
        ownership: tuple[AdapterOwnershipRecord, ...],
        results_by_query: dict[str, AdapterQueryResult],
        warehouse_timestamp: str,
    ) -> None:
        self._catalog = catalog
        self._ownership = ownership
        self._results_by_query = results_by_query
        self._warehouse_timestamp = warehouse_timestamp

    @property
    def adapter_identity(self) -> object:
        raise NotImplementedError

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            virtual_environments=False,
            managed_source_kinds=frozenset({"kafka"}),
            replay_boundary_modes=frozenset(),
            history_prefix_seed=False,
            stable_logical_bindings=False,
            per_relation_atomic_replace=False,
            graph_atomic_publish=False,
            set_difference_comparison=True,
            direct_rebuild=True,
        )

    def capture_warehouse_timestamp(self) -> str:
        return self._warehouse_timestamp

    def close(self) -> None:
        return None

    def compare_readiness(self, request: object) -> tuple:
        raise NotImplementedError

    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        raise NotImplementedError

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        raise NotImplementedError

    def load_catalog(self, database: str) -> CatalogSnapshot:
        return self._catalog

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        return AdapterDeploymentInventory(deployments=(), publish_events=())

    def load_target_ownership(self, database: str) -> tuple[AdapterOwnershipRecord, ...]:
        return self._ownership

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        raise NotImplementedError

    def query(self, statement: str) -> AdapterQueryResult:
        return self._results_by_query[statement]

    def render_cleanup_relations(self, request: object) -> tuple[str, ...]:
        raise NotImplementedError

    def render_ensure_database(self, database: str) -> str:
        raise NotImplementedError

    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        raise NotImplementedError

    def render_persist_metadata_state(self, *, database: str, state: object) -> tuple[str, ...]:
        raise NotImplementedError

    def render_record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> tuple[str, ...]:
        raise NotImplementedError

    def render_remove_target_ownership(
        self, *, database: str, target_database: str, relation_names: tuple[str, ...]
    ) -> tuple[str, ...]:
        raise NotImplementedError

    def render_replace_stable_bindings(self, request: object) -> tuple[str, ...]:
        raise NotImplementedError

    def render_replay_coverage_query(self, request: object) -> str:
        raise NotImplementedError

    def render_replay_from_ownership(self, request: object) -> str:
        raise NotImplementedError

    def render_resource(
        self, *, resource: object, database: str, if_not_exists: bool = False
    ) -> str:
        raise NotImplementedError


_STATE_WAREHOUSE_NOW: str = "2026-08-03 12:00:00.000"
_STATE_NEWEST_EVENT: str = "2026-08-03 11:59:58.000"
_STATE_OLDEST_EVENT: str = "2026-08-01 00:00:00.000"
_STATE_MODEL_NEWEST: str = "2026-08-03 10:00:00.000"

_RAW_COLUMNS: tuple[CatalogColumn, ...] = (
    CatalogColumn(name="kafka_value", type="String"),
    CatalogColumn(name="_replay_partition", type="Int32"),
    CatalogColumn(name="_replay_offset", type="Int64"),
    CatalogColumn(name="_replay_landed_at", type="DateTime64(3)"),
)

_MODEL_LIVE_COLUMNS: tuple[CatalogColumn, ...] = (
    CatalogColumn(name="order_id", type="String"),
    CatalogColumn(name="_replay_partition", type="Int64"),
    CatalogColumn(name="_replay_offset", type="Int64"),
    CatalogColumn(name="_replay_landed_at", type="DateTime64(3)"),
)


def build_state_test_client(*, project_dir: Path) -> TestClient:
    state: DevServerState = DevServerState(
        run_compile=build_compile_callable(project_dir=project_dir)
    )
    connection: FakeAdapterConnection = build_fake_state_connection()
    return TestClient(
        create_dev_app(
            state=state, connection=connection, database="analytics", project_dir=project_dir
        )
    )


def build_fake_state_connection() -> FakeAdapterConnection:
    catalog: CatalogSnapshot = CatalogSnapshot(
        identity=CatalogIdentity(adapter=AdapterIdentity(name="clickhouse"), database="analytics"),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="raw__orders",
                engine="MergeTree",
                columns=_RAW_COLUMNS,
                order_by=("_replay_partition", "_replay_offset"),
            ),
            CatalogRelation(
                name="tbl__orders_clean",
                engine="ReplacingMergeTree",
                columns=_MODEL_LIVE_COLUMNS,
                order_by=("order_id", "_replay_partition", "_replay_offset"),
            ),
        ),
    )
    ownership: tuple[AdapterOwnershipRecord, ...] = (
        AdapterOwnershipRecord(
            database_name="analytics",
            relation_name="tbl__orders_clean",
            resource_kind="table",
            logical_model_name="orders_clean",
            owning_mode="direct",
            tool_version="0",
            replay_coverage=(
                AdapterReplayCoverageRange(
                    driving_input_relation_name="raw__orders",
                    replay_boundary_mode="landed_at",
                    boundary_key="raw__orders",
                    source_partition_column_name=None,
                    source_position_column_name="_replay_offset",
                    source_timestamp_column_name="_replay_landed_at",
                    lower_value=_STATE_OLDEST_EVENT,
                    upper_value=_STATE_MODEL_NEWEST,
                ),
            ),
        ),
    )
    lineage_relations: tuple[str, ...] = ("raw__orders", "tbl__orders_clean")
    results: dict[str, AdapterQueryResult] = {
        build_relation_stats_query(database="analytics"): AdapterQueryResult(
            rows=(
                ("raw__orders", 1000, 4096),
                ("tbl__orders_clean", 900, 2048),
            ),
            column_names=("name", "total_rows", "total_bytes"),
        ),
        build_parts_query(database="analytics"): AdapterQueryResult(
            rows=(("raw__orders", 3), ("tbl__orders_clean", 2)),
            column_names=("table", "parts"),
        ),
        build_extents_query(
            database="analytics", relation_names=lineage_relations
        ): AdapterQueryResult(
            rows=(
                ("raw__orders", _STATE_OLDEST_EVENT, _STATE_NEWEST_EVENT, 1000),
                ("tbl__orders_clean", _STATE_OLDEST_EVENT, _STATE_MODEL_NEWEST, 900),
            ),
            column_names=("relation", "oldest", "newest", "rows"),
        ),
        build_throughput_query(
            database="analytics",
            relation_name="raw__orders",
            window_seconds=3600,
            bucket_seconds=60,
        ): AdapterQueryResult(
            rows=((1754218740, 120), (1754218800, 180)),
            column_names=("bucket", "rows"),
        ),
        build_partitions_query(
            database="analytics", relation_name="raw__orders"
        ): AdapterQueryResult(
            rows=((0, 91822, _STATE_NEWEST_EVENT),),
            column_names=("partition", "max_offset", "newest"),
        ),
        (
            "SELECT count() AS present FROM system.tables "
            "WHERE database = 'analytics' AND name = '_streambuild_invocations'"
        ): AdapterQueryResult(rows=((0,),), column_names=("present",)),
        (
            "SELECT count() AS present FROM system.tables "
            "WHERE database = 'analytics' AND name = '_streambuild_run_events'"
        ): AdapterQueryResult(rows=((1,),), column_names=("present",)),
        (
            "SELECT sequence, toString(emitted_at) AS emitted_at, event_kind, step_id, phase, "
            "payload_json FROM `analytics`.`_streambuild_run_events` "
            "WHERE invocation_id = 'inv-42' ORDER BY sequence"
        ): AdapterQueryResult(
            rows=(
                (1, "2026-08-03 12:00:00.000", "run_started", None, None, '{"command": "build"}'),
                (
                    2,
                    "2026-08-03 12:00:01.000",
                    "statement_completed",
                    "replay_orders",
                    "replay",
                    '{"writtenRows": 42}',
                ),
            ),
            column_names=(
                "sequence",
                "emitted_at",
                "event_kind",
                "step_id",
                "phase",
                "payload_json",
            ),
        ),
        build_replay_count_query(
            database="analytics",
            relation_name="raw__orders",
            time_column="_replay_landed_at",
            start_time=None,
        ): AdapterQueryResult(rows=((1000,),), column_names=("rows",)),
        # The neutral base connection renders the latest-node-status query as ""
        # (unsupported); the fake answers it with one recorded audit outcome.
        "": AdapterQueryResult(
            rows=(
                (
                    "audit",
                    "pipelines/order_events/orders_clean.sql:1",
                    "fingerprint",
                    "passed",
                    "error",
                    0,
                    "2026-08-03 09:00:00.000",
                    '{"sample_column_names": ["order_id"], "sample_rows": []}',
                    None,
                ),
            ),
            column_names=(
                "node_kind",
                "node_identity",
                "definition_fingerprint",
                "current_status",
                "severity",
                "failure_count",
                "completed_at",
                "payload_json",
                "error_message",
            ),
        ),
    }
    return FakeAdapterConnection(
        catalog=catalog,
        ownership=ownership,
        results_by_query=results,
        warehouse_timestamp=_STATE_WAREHOUSE_NOW,
    )


class FakeEmptyResultConnection(FakeAdapterConnection):
    """Returns a zero count for every query; audits therefore pass."""

    def query(self, statement: str) -> AdapterQueryResult:
        return AdapterQueryResult(rows=((0,),), column_names=("value",))
