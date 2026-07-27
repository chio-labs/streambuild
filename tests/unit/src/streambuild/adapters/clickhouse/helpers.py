from collections.abc import Callable, Iterator, Sequence

from sqlglot import parse_one

from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.compile.models import (
    Column,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    KafkaSettings,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.planner.models import (
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    DeploymentWatermarkRecord,
    MetadataState,
    ObjectStateRecord,
    PreparedObjectMapping,
    PublishEventRecord,
)


class FakeRawClickHouseQueryResult:
    """A raw driver result shape used to exercise adapter normalization."""

    def __init__(self, *, column_names: list[str], result_rows: list[list[object]]) -> None:
        self.column_names: Sequence[str] = column_names
        self.result_rows: Sequence[Sequence[object]] = result_rows


class StubRawClickHouseClient:
    """A raw driver client returning one prepared result for every query."""

    def __init__(self, result: FakeRawClickHouseQueryResult) -> None:
        self._result: FakeRawClickHouseQueryResult = result
        self.closed: bool = False

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        del statement
        return self._result

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names

    def close(self) -> None:
        self.closed = True


class SequencedRawClickHouseClient:
    """A raw client returning a prepared result sequence while recording queries."""

    def __init__(self, results: tuple[FakeRawClickHouseQueryResult, ...]) -> None:
        self._results: Iterator[FakeRawClickHouseQueryResult] = iter(results)
        self.statements: list[str] = []

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        self.statements.append(statement)
        return next(self._results)

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names

    def close(self) -> None:
        return None


class FailingRawClickHouseClient:
    """A raw driver client that always raises one prepared driver error."""

    def __init__(self, error: Exception) -> None:
        self._error: Exception = error

    def command(self, statement: str) -> None:
        del statement
        raise self._error

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        del statement
        raise self._error

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names
        raise self._error

    def close(self) -> None:
        raise self._error


class RecordingMetadataMigrationConnection:
    def __init__(
        self,
        *,
        query_results: tuple[AdapterQueryResult, ...],
        command_actions: tuple[Callable[[str], None], ...],
    ) -> None:
        self._query_results: Iterator[AdapterQueryResult] = iter(query_results)
        self.command_actions: Iterator[Callable[[str], None]] = iter(command_actions)
        self.commands: list[str] = []
        self.ensured_databases: list[str] = []
        self.inserted_rows: list[tuple[str, tuple[dict[str, object], ...]]] = []

    def ensure_database(self, database: str) -> None:
        self.ensured_databases.append(database)

    def command(self, statement: str) -> None:
        self.commands.append(statement)
        next(self.command_actions)(statement)

    def query(self, statement: str) -> AdapterQueryResult:
        del statement
        return next(self._query_results)

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        self.inserted_rows.append((table, rows))


def accept_migration_statement(statement: str) -> None:
    del statement


def reject_migration_statement(statement: str) -> None:
    raise RuntimeError(f"interrupted while applying {statement}")


def migration_schema_result() -> AdapterQueryResult:
    return AdapterQueryResult(
        rows=(
            ("streambuild_object_state_snapshots", "deployment_id"),
            ("streambuild_object_state_snapshots", "database_name"),
            ("streambuild_object_state_snapshots", "object_type"),
            ("streambuild_object_state_snapshots", "object_name"),
            ("streambuild_object_state_snapshots", "normalized_fingerprint"),
            ("streambuild_object_state_snapshots", "normalized_query"),
            ("streambuild_object_state_snapshots", "recorded_at"),
            ("streambuild_deployments", "deployment_id"),
            ("streambuild_deployments", "created_at"),
            ("streambuild_deployments", "status"),
            ("streambuild_deployments", "replay_lineage_mode"),
            ("streambuild_deployments", "selected_root_keys_json"),
            ("streambuild_deployments", "warning_codes_json"),
            ("streambuild_deployments", "prepared_object_mappings_json"),
            ("streambuild_deployment_watermarks", "deployment_id"),
            ("streambuild_deployment_watermarks", "root_database_name"),
            ("streambuild_deployment_watermarks", "root_object_type"),
            ("streambuild_deployment_watermarks", "root_object_name"),
            ("streambuild_deployment_watermarks", "anchor_database_name"),
            ("streambuild_deployment_watermarks", "anchor_object_type"),
            ("streambuild_deployment_watermarks", "anchor_object_name"),
            ("streambuild_deployment_watermarks", "boundary_key"),
            ("streambuild_deployment_watermarks", "cutoff_value"),
            ("streambuild_deployment_runtime_details", "deployment_id"),
            ("streambuild_deployment_runtime_details", "root_database_name"),
            ("streambuild_deployment_runtime_details", "root_object_type"),
            ("streambuild_deployment_runtime_details", "root_object_name"),
            ("streambuild_deployment_runtime_details", "state_kind"),
            ("streambuild_deployment_runtime_details", "replay_strategy"),
            ("streambuild_deployment_runtime_details", "active_deployment_id"),
            ("streambuild_deployment_runtime_details", "anchor_database_name"),
            ("streambuild_deployment_runtime_details", "anchor_object_type"),
            ("streambuild_deployment_runtime_details", "anchor_object_name"),
            ("streambuild_deployment_runtime_details", "anchor_physical_name"),
            ("streambuild_deployment_runtime_details", "execution_mode"),
            ("streambuild_deployment_runtime_details", "configured_backfill_mode"),
            ("streambuild_deployment_runtime_details", "execution_lookback_seconds"),
            ("streambuild_deployment_runtime_details", "live_target_names_json"),
            ("streambuild_publish_history", "deployment_id"),
            ("streambuild_publish_history", "published_at"),
            ("streambuild_publish_history", "logical_view_names_json"),
            ("streambuild_state_schema_versions", "version"),
            ("streambuild_state_schema_versions", "applied_at"),
            ("streambuild_target_ownership", "database_name"),
            ("streambuild_target_ownership", "relation_name"),
            ("streambuild_target_ownership", "resource_kind"),
            ("streambuild_target_ownership", "logical_model_database"),
            ("streambuild_target_ownership", "logical_model_name"),
            ("streambuild_target_ownership", "owning_mode"),
            ("streambuild_target_ownership", "tool_version"),
            ("streambuild_target_ownership", "created_at"),
            ("streambuild_target_ownership", "updated_at"),
        )
    )


def build_kafka_table(extra_settings: dict[str, str] | None = None) -> DesiredKafkaTable:
    return DesiredKafkaTable(
        key=ObjectKey(database=None, object_type="kafka_table", name="kafka__orders"),
        deps=(),
        spec=KafkaTableSpec(
            columns=(Column(name="message", type="String"),),
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
                consumer_group="streambuild_orders_orders",
                format="JSONAsString",
                settings=extra_settings,
            ),
        ),
    )


def build_table(
    *, partition_by: str | None, ttl: str | None, settings: dict[str, str] | None
) -> DesiredTable:
    return DesiredTable(
        key=ObjectKey(database=None, object_type="table", name="tbl__orders_enriched"),
        deps=(),
        spec=TableSpec(
            columns=(
                Column(name="order_id", type="String"),
                Column(name="_replay_landed_at", type="DateTime64(3)", default="now64(3)"),
            ),
            storage=TableStorage(
                engine="ReplacingMergeTree(_replay_landed_at)",
                order_by=("order_id", "_replay_landed_at"),
                partition_by=partition_by,
                ttl=ttl,
                settings=settings,
            ),
        ),
    )


def build_materialized_view(*, query: str, database_template: str) -> DesiredMaterializedView:
    return DesiredMaterializedView(
        key=ObjectKey(
            database=None,
            object_type="materialized_view",
            name="mv__orders_enriched",
        ),
        deps=(),
        spec=MaterializedViewSpec(
            source_table_name="raw__orders",
            target_table_name="tbl__orders_enriched",
            query=query,
            database_template=database_template,
        ),
    )


def build_metadata_state() -> MetadataState:
    root_key: ObjectKey = ObjectKey(database=None, object_type="table", name="raw__orders")
    transform_key: ObjectKey = ObjectKey(
        database=None,
        object_type="table",
        name="tbl__orders_enriched",
    )
    return MetadataState(
        object_states=(
            ObjectStateRecord(
                deployment_id="20260408T130000Z_ab12cd",
                key=transform_key,
                normalized_fingerprint="fingerprint_transform",
                normalized_query="SELECT * FROM raw__orders",
                recorded_at="2026-04-08T13:00:00Z",
            ),
        ),
        deployments=(
            DeploymentRecord(
                deployment_id="20260408T130000Z_ab12cd",
                created_at="2026-04-08T13:00:00Z",
                status="backfilling",
                replay_lineage_mode="offsets",
                selected_root_keys=(root_key,),
                warning_codes=("mutable_ref_replay_not_guaranteed",),
                prepared_object_mappings=(
                    PreparedObjectMapping(
                        logical_key=transform_key,
                        physical_name="tbl__orders_enriched__20260408T130000Z_ab12cd",
                    ),
                ),
            ),
        ),
        deployment_watermarks=(
            DeploymentWatermarkRecord(
                deployment_id="20260408T130000Z_ab12cd",
                root_key=transform_key,
                anchor_key=root_key,
                boundary_key="partition:0",
                cutoff_value="12345",
            ),
        ),
        deployment_runtime_details=(
            DeploymentRuntimeDetailRecord(
                deployment_id="20260408T130000Z_ab12cd",
                root_key=transform_key,
                state_kind="active_view_present",
                replay_strategy="bounded_replay",
                active_deployment_id="20260408T120000Z_zz99yy",
                anchor_key=root_key,
                anchor_physical_name="raw__orders__20260408T130000Z_ab12cd",
                execution_mode="seeded_bounded_rebuild",
                configured_backfill_mode="bounded",
                execution_lookback_seconds=604800,
                live_target_names=("tbl__orders_enriched",),
            ),
        ),
        publish_events=(
            PublishEventRecord(
                deployment_id="20260408T130000Z_ab12cd",
                published_at="2026-04-08T13:30:00Z",
                logical_view_names=("tbl__orders_enriched",),
            ),
        ),
    )


def normalize_clickhouse_sql(sql: str) -> str:
    return parse_one(sql, dialect="clickhouse").sql(dialect="clickhouse")
