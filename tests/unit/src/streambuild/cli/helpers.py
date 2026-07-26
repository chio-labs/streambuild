import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterCapabilities,
    AdapterConnectionConfig,
    AdapterIdentity,
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterMetadataState,
    AdapterQueryResult,
    AdapterReplayRequest,
    AdapterStableView,
    AdapterTable,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.audit.main._run_audit import run_audit
from streambuild.cli.audit_backfill.main._run_audit_backfill import run_audit_backfill
from streambuild.cli.backfill.main._run_backfill import run_backfill
from streambuild.cli.backfill.models import BackfillCommandOptions
from streambuild.cli.compile.main._run_compile import run_compile
from streambuild.cli.discover.main._run_discover import run_discover
from streambuild.cli.doctor.main._run_doctor import run_doctor
from streambuild.cli.entry.models import CliEntrypointHandlers
from streambuild.cli.janitor.main._run_janitor import run_janitor
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.cli.publish.main._run_publish import run_publish
from streambuild.cli.reconcile.main._run_reconcile import run_reconcile
from streambuild.cli.repair_active_view.main._run_repair_active_view import run_repair_active_view
from streambuild.cli.test.main._run_test import run_test


def normalize_json_output(output: str) -> str:
    parsed: object = json.loads(output)
    return json.dumps(parsed, sort_keys=True)


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
        relations: tuple[CatalogRelation, ...] = (),
    ) -> None:
        self.statements: list[str] = []
        self.catalog_databases: list[str] = []
        self.closed: bool = False
        self._capabilities: AdapterCapabilities = AdapterCapabilities(
            virtual_environments=virtual_environments,
            managed_source_kinds=managed_source_kinds,
            replay_boundary_modes=replay_boundary_modes,
            history_prefix_seed=history_prefix_seed,
        )
        self._relations: tuple[CatalogRelation, ...] = relations

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

    def command(self, statement: str) -> None:
        self.statements.append(statement)

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return AdapterQueryResult(rows=())

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        del table, rows

    def ensure_database(self, database: str) -> None:
        self.command(f"CREATE DATABASE IF NOT EXISTS {database}")

    def render_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str:
        return ClickHouseAdapter().render_resource(
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
        self.command(
            self.render_resource(
                resource=resource,
                database=database,
                if_not_exists=if_not_exists,
            )
        )

    def migrate_metadata_state(self, database: str) -> None:
        self.ensure_database(database)

    def persist_metadata_state(self, *, database: str, state: AdapterMetadataState) -> None:
        del database, state

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        del request

    def close(self) -> None:
        self.closed = True


class AdapterConnectionProvider:
    def __init__(self, connection: RecordingAdapterConnection) -> None:
        self.connection: RecordingAdapterConnection = connection
        self.config: AdapterConnectionConfig | None = None

    def __call__(self, config: AdapterConnectionConfig) -> RecordingAdapterConnection:
        self.config = config
        return self.connection


class BackfillCommandRunnerAdapter:
    def __init__(self, runner: Callable[..., int]) -> None:
        self._runner: Callable[..., int] = runner

    def __call__(self, *, options: BackfillCommandOptions, client: object) -> int:
        return self._runner(
            pipelines_root=options.pipelines_root,
            database=options.database,
            metadata_database=options.metadata_database,
            selectors=options.selectors,
            deployment_id=options.deployment_id,
            full_refresh=options.full_refresh,
            start_time=options.start_time,
            json_output=options.json_output,
            verbose=options.verbose,
            auto_approve=options.auto_approve,
            client=client,
        )


def handlers_with_overrides(**overrides: object) -> CliEntrypointHandlers:
    has_backfill_override: bool = "run_backfill" in overrides
    backfill_override: object = overrides.pop("run_backfill", run_backfill)
    backfill_handler: Callable[..., int] = {
        False: run_backfill,
        True: BackfillCommandRunnerAdapter(cast(Callable[..., int], backfill_override)),
    }[has_backfill_override]
    return replace(
        CliEntrypointHandlers(
            run_discover=run_discover,
            run_compile=run_compile,
            run_test=run_test,
            run_audit=run_audit,
            run_plan=run_plan,
            run_backfill=backfill_handler,
            run_audit_backfill=run_audit_backfill,
            run_publish=run_publish,
            run_reconcile=run_reconcile,
            run_janitor=run_janitor,
            run_doctor=run_doctor,
            run_repair_active_view=run_repair_active_view,
        ),
        **overrides,
    )


CLI_COMMAND_HANDLER_NAMES: dict[str, str] = {
    "audit backfill": "run_audit_backfill",
    "publish": "run_publish",
    "doctor": "run_doctor",
}

CLI_COMMAND_ARGV: dict[str, tuple[str, ...]] = {
    "audit backfill": ("stb", "audit", "backfill"),
    "publish": ("stb", "publish"),
    "doctor": ("stb", "doctor"),
}


def passthrough_output(output: str) -> str:
    """Return CLI output unchanged, for commands that print text rather than JSON."""

    return output


OUTPUT_NORMALIZERS: dict[bool, Callable[[str], str]] = {
    True: normalize_json_output,
    False: passthrough_output,
}
