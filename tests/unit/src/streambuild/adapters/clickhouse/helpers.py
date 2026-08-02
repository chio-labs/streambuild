from collections.abc import Iterator, Sequence
from typing import cast

from streambuild.adapter.models import (
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from streambuild.adapters.clickhouse.types import RawClickHouseClient
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
from streambuild.compiler.sql_analysis.main._canonicalize_sql import canonicalize_sql


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

    def close(self) -> None:
        return None


class GuardedRenderingClickHouseConnection(ClickHouseConnection):
    """A ClickHouse renderer with prepared read state for cleanup guards."""

    def __init__(
        self, *, catalog: CatalogSnapshot, managed_table_state: InspectedManagedTableState
    ) -> None:
        raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
            FakeRawClickHouseQueryResult(column_names=[], result_rows=[])
        )
        super().__init__(cast(RawClickHouseClient, raw_client))
        self._catalog: CatalogSnapshot = catalog
        self._managed_table_state: InspectedManagedTableState = managed_table_state
        self.inspection_count: int = 0

    def load_catalog(self, database: str) -> CatalogSnapshot:
        del database
        return self._catalog

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        del database
        self.inspection_count += 1
        return self._managed_table_state


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

    def close(self) -> None:
        raise self._error


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
                        logical_model_name="orders_enriched",
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
    return canonicalize_sql(sql=sql, dialect="clickhouse")
