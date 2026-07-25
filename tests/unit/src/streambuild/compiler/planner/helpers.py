from dataclasses import replace
from pathlib import Path

from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    KafkaTableSpec,
    LoadedPipeline,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.shared.types import DesiredObjectType
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.steps import (
    KafkaLandingStep,
    KafkaSettings,
    SchemaChangeBackfillPolicy,
    SchemaChangeBackfillRule,
    TransformStep,
)
from streambuild.spec.models.types import (
    ReplayAnchorMode,
    ReplayLineageMode,
    SchemaChangeBackfillMode,
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


def key_parts(key: ObjectKey) -> tuple[str | None, str, str]:
    return (key.database, key.object_type, key.name)


def with_schema_change_backfill_policy(
    *,
    object_: object,
    mode: SchemaChangeBackfillMode | str,
    lookback_seconds: int | None,
    apply_to_non_breaking: bool,
) -> object:
    if not isinstance(object_, DesiredTable) or object_.name != "tbl__orders_enriched":
        return object_
    rule: SchemaChangeBackfillRule = SchemaChangeBackfillRule(
        mode=SchemaChangeBackfillMode(mode),
        lookback_seconds=lookback_seconds,
    )
    return replace(
        object_,
        schema_change_backfill=SchemaChangeBackfillPolicy(
            non_breaking=rule if apply_to_non_breaking else None,
            breaking=None if apply_to_non_breaking else rule,
        ),
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
