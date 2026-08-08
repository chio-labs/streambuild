import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from textwrap import dedent

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterCapabilities,
    AdapterCapturedReplayRequest,
    AdapterConnectionConfig,
    AdapterDeploymentInventory,
    AdapterDeploymentReplayRequest,
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
    AdapterRelationCleanupRequest,
    AdapterReplayCoverageRequest,
    AdapterStableView,
    AdapterTable,
    AdapterView,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse._helpers.replay import (
    render_clickhouse_replay_coverage_query,
    render_clickhouse_replay_from_capture,
    render_clickhouse_replay_from_deployment,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.audit.main._run_audit import run_audit
from streambuild.cli.build.main._run_build import run_build
from streambuild.cli.compile.main._run_compile import run_compile
from streambuild.cli.deployment.main._run_deployment_diff import run_deployment_diff
from streambuild.cli.deployment.main._run_deployment_list import run_deployment_list
from streambuild.cli.deployment.main._run_deployment_show import run_deployment_show
from streambuild.cli.dev.main._run_dev import run_dev
from streambuild.cli.discover.main._run_discover import run_discover
from streambuild.cli.doctor.main._run_doctor import run_doctor
from streambuild.cli.entry.models import CliEntrypointHandlers
from streambuild.cli.janitor.main._run_janitor import run_janitor
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.cli.promotion.main._run_deployment_promotion import run_deployment_promotion
from streambuild.cli.readiness.main._run_deployment_audit import run_deployment_audit
from streambuild.cli.reconcile.main._run_reconcile import run_reconcile
from streambuild.cli.repair_active_view.main._run_repair_active_view import run_repair_active_view
from streambuild.cli.rollback.main._run_deployment_rollback import run_deployment_rollback
from streambuild.cli.test.main._run_test import run_test

_EMPTY_MANAGED_TABLE_STATE: InspectedManagedTableState = InspectedManagedTableState(
    active_bindings=(),
    physical_candidates=(),
)
_EMPTY_DEPLOYMENT_INVENTORY: AdapterDeploymentInventory = AdapterDeploymentInventory(
    deployments=(),
    publish_events=(),
)


def normalize_json_output(output: str) -> str:
    parsed: object = json.loads(output)
    return json.dumps(parsed, sort_keys=True)


def write_cli_compilation_project(*, project_root: Path, model_sql: str) -> None:
    pipeline_root: Path = project_root / "pipelines" / "orders"
    source_root: Path = project_root / "sources"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    (project_root / "streambuild_project.toml").write_text(
        dedent(
            """
            name = "demo"
            default_target = "test"

            [defaults]
            pipeline_mode = \"virtual\"

            [connection]
            host = "localhost"
            port = 8123
            username = "streambuild"
            password = "streambuild"

            [targets.test]
            database = "analytics"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (source_root / "orders.yml").write_text(
        dedent(
            """
            sources:
              - name: orders
                kind: kafka
                broker_list: kafka:9092
                topic: source.orders
                replay_boundary: {mode: offsets}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (pipeline_root / "orders_enriched.sql").write_text(
        dedent(model_sql).strip() + "\n",
        encoding="utf-8",
    )


def write_cli_target_project(*, project_root: Path, local_contents: str) -> None:
    write_cli_compilation_project(
        project_root=project_root,
        model_sql="""
        MODEL (order_by ["order_id"]);
        SELECT order_id::UInt64 AS order_id FROM __source("orders")
        """,
    )
    (project_root / "streambuild_project.toml").write_text(
        dedent(
            """
            name = "target_project"
            default_target = "dev"

            [targets.dev]
            database = "${database_name}"
            [targets.dev.vars]
            database_name = "dev_database"

            [targets.private]
            database = "${database_name}"
            [targets.private.vars]
            database_name = "private_database"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (project_root / "streambuild_local.toml").write_text(
        dedent(local_contents).strip() + "\n",
        encoding="utf-8",
    )


class FakeCliClickHouseClient:
    def close(self) -> None:
        return None


class RecordingAdapterConnection(AdapterConnection):
    def __init__(
        self,
        *,
        virtual_environments: bool = True,
        managed_source_kinds: frozenset[str] = frozenset({"kafka"}),
        replay_boundary_modes: frozenset[AdapterReplayBoundaryMode] = frozenset(
            AdapterReplayBoundaryMode
        ),
        history_prefix_seed: bool = True,
        stable_logical_bindings: bool = True,
        per_relation_atomic_replace: bool = True,
        graph_atomic_publish: bool = False,
        set_difference_comparison: bool = True,
        direct_rebuild: bool = True,
        relations: tuple[CatalogRelation, ...] = (),
        managed_table_state: InspectedManagedTableState = _EMPTY_MANAGED_TABLE_STATE,
        readiness_observations: tuple[AdapterReadinessRootObservation, ...] = (),
        deployment_inventory: AdapterDeploymentInventory = _EMPTY_DEPLOYMENT_INVENTORY,
        observation_statements: tuple[str, ...] = (),
        required_artifact_path: Path | None = None,
    ) -> None:
        self.statements: list[str] = []
        self.catalog_databases: list[str] = []
        self.closed: bool = False
        self.binding_requests: list[AdapterBindingReplacementRequest] = []
        self.readiness_requests: list[AdapterReadinessRequest] = []
        self.cleanup_requests: list[AdapterRelationCleanupRequest] = []
        self._capabilities: AdapterCapabilities = AdapterCapabilities(
            virtual_environments=virtual_environments,
            managed_source_kinds=managed_source_kinds,
            replay_boundary_modes=replay_boundary_modes,
            history_prefix_seed=history_prefix_seed,
            stable_logical_bindings=stable_logical_bindings,
            per_relation_atomic_replace=per_relation_atomic_replace,
            graph_atomic_publish=graph_atomic_publish,
            set_difference_comparison=set_difference_comparison,
            direct_rebuild=direct_rebuild,
        )
        self._relations: tuple[CatalogRelation, ...] = relations
        self._managed_table_state: InspectedManagedTableState = managed_table_state
        self._readiness_observations: tuple[AdapterReadinessRootObservation, ...] = (
            readiness_observations
        )
        self._deployment_inventory: AdapterDeploymentInventory = deployment_inventory
        self._observation_statements: tuple[str, ...] = observation_statements
        self._required_artifact_path: Path | None = required_artifact_path
        self.artifact_seen_before_execution: bool = False
        self.workflow_mutation_statements: list[str] = []
        self.invocation_observations: list[AdapterInvocationRecord] = []
        self.node_result_observations: list[AdapterNodeResultRecord] = []

    @property
    def adapter_identity(self) -> AdapterIdentity:
        return AdapterIdentity(name="clickhouse")

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def load_catalog(self, database: str) -> CatalogSnapshot:
        self.catalog_databases.append(database)
        return CatalogSnapshot(
            identity=CatalogIdentity(adapter=self.adapter_identity, database=database),
            warehouse_timezone="UTC",
            relations=self._relations,
        )

    def metadata_columns(self, *, database: str, table: str) -> frozenset[str]:
        del database, table
        return frozenset()

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        del database
        return self._managed_table_state

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return AdapterQueryResult(rows=())

    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        self.artifact_seen_before_execution = bool(
            self._required_artifact_path is not None and self._required_artifact_path.exists()
        )
        self.statements.append(statement)
        self.workflow_mutation_statements.append(statement)
        return AdapterMutationResult()

    def render_terminal_observations(
        self,
        *,
        database: str,
        invocation: AdapterInvocationRecord,
        node_results: tuple[AdapterNodeResultRecord, ...],
    ) -> tuple[str, ...]:
        del database
        self.invocation_observations.append(invocation)
        self.node_result_observations.extend(node_results)
        return self._observation_statements

    def capture_warehouse_timestamp(self) -> str:
        return "2026-07-31 12:00:00.000"

    def render_ensure_database(self, database: str) -> str:
        return f"CREATE DATABASE IF NOT EXISTS {database};"

    def render_resource(
        self,
        *,
        resource: AdapterManagedSource
        | AdapterTable
        | AdapterMaterializedView
        | AdapterView
        | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        return ClickHouseAdapter().render_resource(
            resource=resource,
            database=database,
            if_not_exists=if_not_exists,
        )

    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        del database
        return ()

    def render_persist_metadata_state(
        self, *, database: str, state: AdapterMetadataState
    ) -> tuple[str, ...]:
        del database, state
        return ()

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory:
        del database
        return self._deployment_inventory

    def load_direct_fingerprints(
        self, *, database: str, logical_model_identities: tuple[str, ...]
    ) -> AdapterDirectFingerprintSnapshot:
        del database, logical_model_identities
        return AdapterDirectFingerprintSnapshot(status="absent", baselines=())

    def render_replay_coverage_query(self, request: AdapterReplayCoverageRequest) -> str:
        return render_clickhouse_replay_coverage_query(request)

    def render_replay_from_capture(self, request: AdapterCapturedReplayRequest) -> str:
        return render_clickhouse_replay_from_capture(request)

    def render_replay_from_deployment(
        self, request: AdapterDeploymentReplayRequest
    ) -> tuple[str, ...]:
        return render_clickhouse_replay_from_deployment(request)

    def compare_readiness(
        self, request: AdapterReadinessRequest
    ) -> tuple[AdapterReadinessRootObservation, ...]:
        self.readiness_requests.append(request)
        return self._readiness_observations

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        del request
        return ()

    def render_cleanup_relations(self, request: AdapterRelationCleanupRequest) -> tuple[str, ...]:
        del request
        return ()

    def close(self) -> None:
        self.closed = True


class AdapterConnectionProvider:
    def __init__(self, connection: RecordingAdapterConnection) -> None:
        self.connection: RecordingAdapterConnection = connection
        self.config: AdapterConnectionConfig | None = None

    def __call__(self, config: AdapterConnectionConfig) -> RecordingAdapterConnection:
        self.config = config
        return self.connection


def handlers_with_overrides(**overrides: object) -> CliEntrypointHandlers:
    return replace(
        CliEntrypointHandlers(
            run_discover=run_discover,
            run_compile=run_compile,
            run_test=run_test,
            run_audit=run_audit,
            run_plan=run_plan,
            run_build=run_build,
            run_deployment_diff=run_deployment_diff,
            run_deployment_list=run_deployment_list,
            run_deployment_show=run_deployment_show,
            run_deployment_audit=run_deployment_audit,
            run_deployment_promote=run_deployment_promotion,
            run_deployment_rollback=run_deployment_rollback,
            run_reconcile=run_reconcile,
            run_janitor=run_janitor,
            run_doctor=run_doctor,
            run_repair_active_view=run_repair_active_view,
            run_dev=run_dev,
        ),
        **overrides,
    )


CLI_COMMAND_HANDLER_NAMES: dict[str, str] = {
    "deployment audit": "run_deployment_audit",
    "deployment diff": "run_deployment_diff",
    "deployment promote": "run_deployment_promote",
    "deployment rollback": "run_deployment_rollback",
    "doctor": "run_doctor",
}

CLI_COMMAND_ARGV: dict[str, tuple[str, ...]] = {
    "deployment audit": ("stb", "deployment", "audit", "deployment-id"),
    "deployment diff": ("stb", "deployment", "diff", "deployment-id"),
    "deployment promote": ("stb", "deployment", "promote", "deployment-id"),
    "deployment rollback": (
        "stb",
        "deployment",
        "rollback",
        "deployment-id",
        "--auto-approve",
    ),
    "doctor": ("stb", "doctor"),
}


def passthrough_output(output: str) -> str:
    """Return CLI output unchanged, for commands that print text rather than JSON."""

    return output


OUTPUT_NORMALIZERS: dict[bool, Callable[[str], str]] = {
    True: normalize_json_output,
    False: passthrough_output,
}
