from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterCapabilities,
    AdapterIdentity,
    AdapterQueryResult,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
)
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    Column,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.compile.models import (
    KafkaSettings as CompiledKafkaSettings,
)
from streambuild.compiler.compile.types import DesiredObjectType
from streambuild.compiler.desired_state.main.build_desired_state import build_desired_state
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    ReplayBoundary,
    ReplayBoundaryColumns,
    SchemaChangeBackfillPolicy,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
)
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualStateInspection,
    ActualTable,
    RootDeploymentInspection,
)

EXAMPLE_PIPELINE_FILE_PATH: Path = Path(
    "tests/fixtures/basic_project/pipelines/orders/pipeline.yml"
)


class SnapshotRecordingConnection(AdapterConnection):
    def __init__(
        self,
        *,
        catalog: CatalogSnapshot,
        metadata_result: AdapterQueryResult,
        virtual_environments: bool,
    ) -> None:
        self._catalog: CatalogSnapshot = catalog
        self._metadata_result: AdapterQueryResult = metadata_result
        self._capabilities: AdapterCapabilities = AdapterCapabilities(
            virtual_environments=virtual_environments
        )
        self.catalog_load_count: int = 0
        self.query_count: int = 0

    @property
    def adapter_identity(self) -> AdapterIdentity:
        return self._catalog.identity.adapter

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def load_catalog(self, database: str) -> CatalogSnapshot:
        del database
        self.catalog_load_count += 1
        return self._catalog

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> AdapterQueryResult:
        del statement
        self.query_count += 1
        return self._metadata_result

    def insert_rows(self, *, table: str, rows: tuple[dict[str, object], ...]) -> None:
        del table, rows

    def close(self) -> None:
        return None


def build_snapshot_catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        identity=CatalogIdentity(
            adapter=AdapterIdentity(name="clickhouse"),
            database="analytics",
        ),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="tbl__orders",
                engine="MergeTree",
                columns=(CatalogColumn(name="order_id", type="String"),),
            ),
        ),
    )


def build_example_desired_state() -> DesiredState:
    loaded_pipeline: LoadedPipeline = load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)
    return build_desired_state((compile_pipeline(loaded_pipeline),))


def build_single_transform_desired_state(
    *,
    query: str,
    replay_lineage_mode: ReplayLineageMode | str = ReplayLineageMode.OFFSETS,
    replay_anchor: ReplayAnchorMode | str = ReplayAnchorMode.AUTO,
    order_by: tuple[str, ...] = ("order_id",),
    supporting_transforms: tuple[tuple[str, str, tuple[str, ...]], ...] = (),
) -> DesiredState:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    resolved_replay_anchor: ReplayAnchorMode = ReplayAnchorMode(replay_anchor)
    supporting_transform_steps: list[TransformStep] = [
        TransformStep(
            name=name,
            source="orders",
            engine="MergeTree()",
            order_by=list(transform_order_by),
            query=transform_query,
        )
        for name, transform_query, transform_order_by in supporting_transforms
    ]
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
        ),
        transforms=[
            *supporting_transform_steps,
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=list(order_by),
                query=query,
                replay_anchor=resolved_replay_anchor,
            ),
        ],
        replay_lineage_mode=resolved_replay_lineage_mode,
    )
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=EXAMPLE_PIPELINE_FILE_PATH,
    )
    return build_desired_state((compile_pipeline(loaded_pipeline),))


def build_preservation_matrix_compiled_pipeline(
    *, source_ownership: str, replay_lineage_mode: ReplayLineageMode | str
) -> CompiledPipeline:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    builder: Callable[[ReplayLineageMode], CompiledPipeline] = PRESERVATION_PIPELINE_BUILDERS[
        source_ownership
    ]
    return builder(resolved_replay_lineage_mode)


def _build_managed_preservation_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode,
) -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="preservation_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
            ),
        ),
        transforms=[_build_preservation_transform(replay_lineage_mode)],
        replay_lineage_mode=replay_lineage_mode,
    )
    return compile_pipeline(LoadedPipeline(pipeline=pipeline, file_path=EXAMPLE_PIPELINE_FILE_PATH))


def _build_adopted_preservation_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode,
) -> CompiledPipeline:
    replay_boundary_mode: ReplayBoundaryMode = ReplayBoundaryMode(replay_lineage_mode)
    pipeline: Pipeline = Pipeline(
        name="preservation_pipeline",
        source=ExternalTableSourceStep(
            name="orders",
            kind=PRESERVATION_EXTERNAL_SOURCE_KIND_BY_MODE[replay_lineage_mode],
            table_name="orders_existing",
            replay_boundary=ReplayBoundary(
                mode=replay_boundary_mode,
                columns=PRESERVATION_BOUNDARY_COLUMNS_BY_MODE[replay_lineage_mode],
            ),
        ),
        transforms=[_build_preservation_transform(replay_lineage_mode)],
    )
    return compile_pipeline(LoadedPipeline(pipeline=pipeline, file_path=EXAMPLE_PIPELINE_FILE_PATH))


def _build_preservation_transform(replay_lineage_mode: ReplayLineageMode) -> TransformStep:
    return TransformStep(
        name="orders_enriched",
        source="orders",
        engine="MergeTree()",
        order_by=["order_id"],
        query=(
            "SELECT CAST(order_id AS String) AS order_id, "
            + PRESERVATION_PROJECTION_BY_MODE[replay_lineage_mode]
            + ' FROM __ref("orders")'
        ),
        replay_anchor=ReplayAnchorMode.NEVER,
    )


PRESERVATION_PIPELINE_BUILDERS: dict[str, Callable[[ReplayLineageMode], CompiledPipeline]] = {
    "managed": _build_managed_preservation_compiled_pipeline,
    "adopted": _build_adopted_preservation_compiled_pipeline,
}
PRESERVATION_EXTERNAL_SOURCE_KIND_BY_MODE: dict[ReplayLineageMode, SourceKind] = {
    ReplayLineageMode.OFFSETS: SourceKind.KAFKA,
    ReplayLineageMode.TIMESTAMP: SourceKind.KAFKA,
    ReplayLineageMode.CURSOR: SourceKind.STREAM_TABLE,
}
PRESERVATION_BOUNDARY_COLUMNS_BY_MODE: dict[ReplayLineageMode, ReplayBoundaryColumns] = {
    ReplayLineageMode.OFFSETS: ReplayBoundaryColumns(
        partition="event_partition",
        offset="event_offset",
        timestamp="event_timestamp",
    ),
    ReplayLineageMode.TIMESTAMP: ReplayBoundaryColumns(timestamp="event_timestamp"),
    ReplayLineageMode.CURSOR: ReplayBoundaryColumns(
        timestamp="event_timestamp",
        cursor="event_cursor",
    ),
}
PRESERVATION_PROJECTION_BY_MODE: dict[ReplayLineageMode, str] = {
    ReplayLineageMode.OFFSETS: (
        "CAST(_replay_partition AS Int32) AS _replay_partition, "
        "CAST(_replay_offset AS Int64) AS _replay_offset"
    ),
    ReplayLineageMode.TIMESTAMP: ("CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp"),
    ReplayLineageMode.LANDED_AT: ("CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at"),
    ReplayLineageMode.CURSOR: "CAST(_replay_cursor AS UInt64) AS _replay_cursor",
}


def build_mutable_ref_desired_state() -> DesiredState:
    return build_single_transform_desired_state(
        query=(
            "SELECT CAST(order_id AS UInt64) AS order_id, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders") LEFT JOIN '
            '__ref("customers", ref_type="mutable") USING customer_id'
        ),
        supporting_transforms=(
            (
                "customers",
                'SELECT CAST(customer_id AS UInt64) AS customer_id FROM __ref("orders")',
                ("customer_id",),
            ),
        ),
    )


def build_key(database: str | None, object_type: str, name: str) -> ObjectKey:
    return ObjectKey(database=database, object_type=DesiredObjectType(object_type), name=name)


def build_example_desired_state_with_backfill_policy(
    *, schema_change_backfill: SchemaChangeBackfillPolicy | None
) -> DesiredState:
    """Build the example desired state with a schema-change policy on every transform."""

    loaded_pipeline: LoadedPipeline = load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)
    pipeline_with_policy: Pipeline = replace(
        loaded_pipeline.pipeline,
        transforms=[
            replace(transform_step, schema_change_backfill=schema_change_backfill)
            for transform_step in loaded_pipeline.pipeline.transforms
        ],
    )
    return build_desired_state(
        (compile_pipeline(replace(loaded_pipeline, pipeline=pipeline_with_policy)),)
    )


def build_example_actual_state() -> ActualState:
    desired_state: DesiredState = build_example_desired_state()
    kafka_table: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[
        0
    ]
    landing_mv: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[
        1
    ]
    raw_table: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = desired_state.objects[3]
    assert isinstance(kafka_table, DesiredKafkaTable)
    assert isinstance(landing_mv, DesiredMaterializedView)
    assert isinstance(raw_table, DesiredTable)

    return ActualState(
        objects=(
            ActualKafkaTable(
                key=kafka_table.key,
                spec=KafkaTableSpec(
                    columns=kafka_table.spec.columns,
                    kafka=kafka_table.spec.kafka,
                ),
            ),
            ActualMaterializedView(
                key=landing_mv.key,
                spec=MaterializedViewSpec(
                    source_table_name=landing_mv.spec.source_table_name,
                    target_table_name=landing_mv.spec.target_table_name,
                    query=landing_mv.spec.query,
                ),
            ),
            ActualTable(
                key=raw_table.key,
                spec=TableSpec(
                    columns=raw_table.spec.columns,
                    storage=TableStorage(
                        engine=raw_table.spec.storage.engine,
                        order_by=raw_table.spec.storage.order_by,
                        partition_by=raw_table.spec.storage.partition_by,
                        ttl=raw_table.spec.storage.ttl,
                        settings={"index_granularity": "4096"},
                    ),
                ),
            ),
        )
    )


def build_actual_state_matching_desired(desired_state: DesiredState) -> ActualState:
    actual_object_builders: dict[type[object], Callable[..., object]] = {
        DesiredKafkaTable: ActualKafkaTable,
        DesiredMaterializedView: ActualMaterializedView,
        DesiredTable: ActualTable,
    }
    actual_objects: tuple[ActualKafkaTable | ActualMaterializedView | ActualTable, ...] = tuple(
        cast(
            ActualKafkaTable | ActualMaterializedView | ActualTable,
            actual_object_builders[type(desired_object)](
                key=desired_object.key,
                spec=desired_object.spec,
            ),
        )
        for desired_object in desired_state.objects
    )
    return ActualState(objects=actual_objects)


def build_actual_objects() -> tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...]:
    kafka_spec: KafkaTableSpec = KafkaTableSpec(
        columns=(Column(name="message", type="String"),),
        kafka=CompiledKafkaSettings(
            broker_list="kafka:9092",
            topic="source.orders.created",
            consumer_group="streambuild_orders_orders",
            format="JSONAsString",
            settings={"kafka_num_consumers": "4"},
        ),
    )
    table_spec: TableSpec = TableSpec(
        columns=(
            Column(name="order_id", type="String"),
            Column(name="updated_at", type="DateTime64(3)"),
        ),
        storage=TableStorage(
            engine="ReplacingMergeTree(updated_at)",
            order_by=("order_id", "updated_at"),
            partition_by="toYYYYMM(updated_at)",
            ttl="toDateTime(updated_at) + INTERVAL 30 DAY",
            settings={"index_granularity": "8192"},
        ),
    )
    materialized_view_spec: MaterializedViewSpec = MaterializedViewSpec(
        source_table_name="raw__orders",
        target_table_name="tbl__orders_enriched",
        query="SELECT * FROM raw__orders",
    )
    return (
        ActualTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_TABLE,
                name="tbl__orders_enriched",
            ),
            spec=table_spec,
        ),
        ActualMaterializedView(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
                name="mv__orders_enriched",
            ),
            spec=materialized_view_spec,
        ),
        ActualKafkaTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_KAFKA_TABLE,
                name="kafka__orders",
            ),
            spec=kafka_spec,
        ),
    )


def build_projection_characterization_inputs() -> tuple[DesiredState, ActualStateInspection]:
    kafka_key: ObjectKey = ObjectKey(database=None, object_type="kafka_table", name="kafka__orders")
    raw_key: ObjectKey = ObjectKey(database=None, object_type="table", name="raw__orders")
    landing_mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type="materialized_view",
        name="mv__orders_landing",
    )
    transform_key: ObjectKey = ObjectKey(
        database=None, object_type="table", name="tbl__orders_enriched"
    )
    raw_storage: TableStorage = TableStorage(
        engine="MergeTree()",
        order_by=("order_id",),
        partition_by="toYYYYMM(created_at)",
        ttl="created_at + INTERVAL 30 DAY",
        settings={"index_granularity": "8192"},
    )
    desired_state: DesiredState = DesiredState(
        objects=(
            DesiredKafkaTable(
                key=kafka_key,
                deps=(),
                spec=KafkaTableSpec(
                    columns=(Column(name="message", type="String"),),
                    kafka=CompiledKafkaSettings(
                        broker_list="kafka:9092",
                        topic="source.orders.created",
                        consumer_group="streambuild_orders_orders",
                        format="JSONAsString",
                        settings={"kafka_num_consumers": "4"},
                    ),
                ),
            ),
            DesiredTable(
                key=raw_key,
                deps=(kafka_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
            DesiredMaterializedView(
                key=landing_mv_key,
                deps=(kafka_key, raw_key),
                spec=MaterializedViewSpec(
                    source_table_name="kafka__orders",
                    target_table_name="raw__orders",
                    query="SELECT message AS order_id FROM kafka__orders",
                ),
            ),
            DesiredTable(
                key=transform_key,
                deps=(raw_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_key}),
        mutable_ref_warning_keys=frozenset(),
    )
    inspection: ActualStateInspection = ActualStateInspection(
        existing_names=frozenset({kafka_key.name, raw_key.name, landing_mv_key.name}),
        active_deployment_by_root={
            transform_key: RootDeploymentInspection(
                root_key=transform_key,
                state_kind="active_view_present",
                active_deployment_id="dep_a",
            )
        },
        object_state_by_deployment_and_key={},
        latest_object_state_by_key={},
        active_physical_names_by_logical_name={transform_key.name: "tbl__orders_enriched__dep_a"},
        active_table_specs_by_name={
            "tbl__orders_enriched__dep_a": TableSpec(
                columns=(Column(name="order_id", type="String"),),
                storage=TableStorage(
                    engine="MergeTree()",
                    order_by=("order_id",),
                    ttl=None,
                    settings=None,
                ),
            )
        },
    )
    return desired_state, inspection


KeyParts: type = tuple[str | None, str, str]


def key_parts(key: ObjectKey) -> KeyParts:
    """Return a key as a comparable tuple."""

    return (key.database, key.object_type, key.name)


def optional_key_parts(key: ObjectKey | None) -> KeyParts | None:
    """Return a key as a comparable tuple, preserving an absent key as None."""

    resolvers: dict[type[object], Callable[[], tuple[str | None, str, str] | None]] = {
        type(None): lambda: None,
        ObjectKey: lambda: key_parts(cast(ObjectKey, key)),
    }
    return resolvers[type(key)]()
