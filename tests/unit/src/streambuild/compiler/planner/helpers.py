from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
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

EXAMPLE_PIPELINE_FILE_PATH: Path = Path(
    "tests/fixtures/basic_project/pipelines/orders/pipeline.yml"
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
