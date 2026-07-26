from collections.abc import Callable

from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledManagedSource,
    CompiledPipeline,
    DesiredState,
)
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.executor.backfill.models import BackfillBootstrapRequest
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.steps import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    KafkaSettings,
    ReplayBoundary,
    ReplayBoundaryColumns,
    TransformStep,
)
from streambuild.spec.models.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
)
from tests.integration.src.streambuild.clickhouse.render._helpers.create_materialized_view.helpers import (  # noqa: E501
    build_compiled_example_pipeline,
)
from tests.unit.src.streambuild.compiler.planner.helpers import EXAMPLE_PIPELINE_FILE_PATH

KAFKA_TOPIC_PROJECTION: dict[bool, str] = {
    True: "CAST(kafka_topic AS String) AS kafka_topic, ",
    False: "",
}

SCALAR_REPLAY_PROJECTION: dict[ReplayLineageMode, str] = {
    ReplayLineageMode.TIMESTAMP: "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp ",
    ReplayLineageMode.LANDED_AT: "CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at ",
}
LANDED_AT_REPLAY_PROJECTION: str = SCALAR_REPLAY_PROJECTION[ReplayLineageMode.LANDED_AT]


def build_backfill_bootstrap_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
) -> BackfillBootstrapRequest:
    desired_state: DesiredState = build_desired_state(
        (compile_pipeline(load_pipeline_file(EXAMPLE_PIPELINE_FILE_PATH)),)
    )
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
    )


def build_compiled_pipeline() -> CompiledPipeline:
    return build_compiled_example_pipeline()


def build_scalar_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
    replay_lineage_mode: ReplayLineageMode | str,
) -> BackfillBootstrapRequest:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline(
        resolved_replay_lineage_mode
    )
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=resolved_replay_lineage_mode,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_scalar_replay_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode | str,
) -> CompiledPipeline:
    return build_named_scalar_replay_compiled_pipeline(
        replay_lineage_mode=ReplayLineageMode(replay_lineage_mode),
        pipeline_name="orders_pipeline",
        source_name="orders",
        transform_name="orders_enriched",
        topic="source.orders.created",
        include_kafka_topic=False,
    )


def build_named_scalar_replay_compiled_pipeline(
    *,
    replay_lineage_mode: ReplayLineageMode | str,
    pipeline_name: str,
    source_name: str,
    transform_name: str,
    topic: str,
    include_kafka_topic: bool = False,
) -> CompiledPipeline:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    query: str = (
        "SELECT CAST(kafka_key AS String) AS order_id, "
        + KAFKA_TOPIC_PROJECTION[include_kafka_topic]
        + SCALAR_REPLAY_PROJECTION.get(resolved_replay_lineage_mode, LANDED_AT_REPLAY_PROJECTION)
        + f'FROM __ref("{source_name}")'
    )

    pipeline: Pipeline = Pipeline(
        name=pipeline_name,
        source=KafkaLandingStep(
            name=source_name,
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic=topic,
            ),
        ),
        transforms=[
            TransformStep(
                name=transform_name,
                source=source_name,
                engine="MergeTree()",
                order_by=["order_id"],
                query=query,
                replay_anchor=ReplayAnchorMode.NEVER,
            )
        ],
        replay_lineage_mode=resolved_replay_lineage_mode,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_offset_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    compiled_pipeline: CompiledPipeline = build_offset_replay_compiled_pipeline()
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_reference_join_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    desired_state: DesiredState = build_desired_state((build_reference_join_compiled_pipeline(),))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_reference_join_region_lookup_only_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    desired_state: DesiredState = build_desired_state(
        (build_reference_join_region_lookup_only_compiled_pipeline(),)
    )
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_external_source_offset_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    compiled_pipeline: CompiledPipeline = build_external_source_offset_replay_compiled_pipeline()
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_external_source_cursor_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    start_time: str | None = None,
) -> BackfillBootstrapRequest:
    compiled_pipeline: CompiledPipeline = build_external_source_cursor_replay_compiled_pipeline()
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.CURSOR,
        deployment_id=deployment_id,
        start_time=start_time,
        start_time_keys=(
            frozenset({compiled_pipeline.transforms[0].target_table.key})
            if start_time is not None
            else frozenset()
        ),
        created_at=created_at,
        stabilization_seconds=0.0,
    )


def build_aggregate_offset_replay_request(
    *,
    database: str,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    compiled_pipeline: CompiledPipeline = build_aggregate_offset_replay_compiled_pipeline()
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=database,
        metadata_database=database,
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_offset_replay_compiled_pipeline() -> CompiledPipeline:
    return build_named_offset_replay_compiled_pipeline(include_kafka_topic=False)


def build_reference_join_compiled_pipeline() -> CompiledPipeline:
    return _build_reference_join_compiled_pipeline(include_enriched_orders=True)


def build_reference_join_region_lookup_only_compiled_pipeline() -> CompiledPipeline:
    return _build_reference_join_compiled_pipeline(include_enriched_orders=False)


def _build_reference_join_compiled_pipeline(*, include_enriched_orders: bool) -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="region_lookup",
                source="orders",
                engine="MergeTree()",
                order_by=["region"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS region, "
                    "CAST(upper(kafka_key) AS String) AS region_display, "
                    "CAST(_replay_partition AS Int64) AS _replay_partition, "
                    "CAST(_replay_offset AS Int64) AS _replay_offset "
                    'FROM __ref("orders")'
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
            ),
            *(
                (
                    TransformStep(
                        name="enriched_orders",
                        source="orders",
                        engine="MergeTree()",
                        order_by=["order_id", "_replay_partition", "_replay_offset"],
                        query=(
                            "SELECT CAST(o.kafka_key AS String) AS order_id, "
                            "CAST(r.region_display AS String) AS region_display, "
                            "CAST(o._replay_partition AS Int64) AS _replay_partition, "
                            "CAST(o._replay_offset AS Int64) AS _replay_offset "
                            'FROM __ref("orders") AS o '
                            'LEFT JOIN __ref("region_lookup", ref_type="reference") AS r '
                            "ON CAST(o.kafka_key AS String) = r.region"
                        ),
                        replay_anchor=ReplayAnchorMode.NEVER,
                    ),
                )
                if include_enriched_orders
                else ()
            ),
        ],
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_external_source_offset_replay_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=ExternalTableSourceStep(
            name="orders",
            kind=SourceKind.KAFKA,
            table_name="orders_existing",
            replay_boundary=ReplayBoundary(
                mode=ReplayBoundaryMode.OFFSETS,
                columns=ReplayBoundaryColumns(
                    partition="event_partition",
                    offset="event_offset",
                    landed_at="event_landed_at",
                ),
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(order_id AS String) AS order_id, "
                    "CAST(event_partition AS Int64) AS _replay_partition, "
                    "CAST(event_offset AS Int64) AS _replay_offset "
                    'FROM __ref("orders")'
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
            )
        ],
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_external_source_cursor_replay_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=ExternalTableSourceStep(
            name="orders",
            kind=SourceKind.STREAM_TABLE,
            table_name="orders_existing",
            replay_boundary=ReplayBoundary(
                mode=ReplayBoundaryMode.CURSOR,
                columns=ReplayBoundaryColumns(
                    cursor="event_cursor",
                    timestamp="event_timestamp",
                ),
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(order_id AS String) AS order_id, "
                    "CAST(_replay_cursor AS UInt64) AS _replay_cursor "
                    'FROM __ref("orders")'
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
            )
        ],
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_aggregate_offset_replay_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="hourly_order_volume",
                source="orders",
                engine="MergeTree()",
                order_by=["event_hour"],
                query=(
                    "SELECT CAST(toStartOfHour(_replay_timestamp) AS DateTime64(3)) "
                    "AS event_hour, "
                    "CAST(count() AS UInt64) AS order_event_count "
                    'FROM __ref("orders") AS item_rows '
                    "GROUP BY event_hour"
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
            )
        ],
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_changed_aggregate_offset_replay_compiled_pipeline(
    *,
    bounded_replay_fallback: BoundedReplayFallback | str = BoundedReplayFallback.FULL_REFRESH,
) -> CompiledPipeline:
    resolved_bounded_replay_fallback: BoundedReplayFallback = BoundedReplayFallback(
        bounded_replay_fallback
    )
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="hourly_order_volume",
                source="orders",
                engine="MergeTree()",
                order_by=["event_hour"],
                query=(
                    "SELECT CAST(toStartOfHour(_replay_timestamp) AS DateTime64(3)) "
                    "AS event_hour, "
                    "CAST(count() AS UInt64) AS order_event_count, "
                    "CAST('changed' AS String) AS replay_marker "
                    'FROM __ref("orders") AS item_rows '
                    "GROUP BY event_hour"
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
                bounded_replay_fallback=resolved_bounded_replay_fallback,
            )
        ],
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_named_offset_replay_compiled_pipeline(
    *, include_kafka_topic: bool = False
) -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS order_id, "
                    + KAFKA_TOPIC_PROJECTION[include_kafka_topic]
                    + "CAST(_replay_partition AS Int64) AS _replay_partition, "
                    "CAST(_replay_offset AS Int64) AS _replay_offset "
                    'FROM __ref("orders")'
                ),
                replay_anchor=ReplayAnchorMode.NEVER,
            )
        ],
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_changed_scalar_replay_compiled_pipeline(
    replay_lineage_mode: ReplayLineageMode | str,
) -> CompiledPipeline:
    return build_named_scalar_replay_compiled_pipeline(
        replay_lineage_mode=ReplayLineageMode(replay_lineage_mode),
        pipeline_name="orders_pipeline",
        source_name="orders",
        transform_name="orders_enriched",
        topic="source.orders.created",
        include_kafka_topic=True,
    )


def build_changed_offset_replay_compiled_pipeline() -> CompiledPipeline:
    return build_named_offset_replay_compiled_pipeline(include_kafka_topic=True)


def build_raw_orders_row(
    *,
    kafka_key: str,
    _replay_partition: int,
    _replay_offset: int,
    _replay_timestamp: str,
    _replay_landed_at: str,
) -> tuple[object, ...]:
    return (
        kafka_key,
        "{}",
        "source.orders.created",
        _replay_partition,
        _replay_offset,
        _replay_timestamp,
        "",
        _replay_landed_at,
    )


def build_external_source_orders_row(
    *,
    order_id: str,
    event_partition: int,
    event_offset: int,
    event_timestamp: str,
    event_landed_at: str,
) -> tuple[object, ...]:
    return (
        order_id,
        event_partition,
        event_offset,
        event_timestamp,
        event_landed_at,
    )


def build_external_source_cursor_orders_row(
    *,
    order_id: str,
    event_cursor: int,
    event_timestamp: str,
) -> tuple[object, ...]:
    return (order_id, event_cursor, event_timestamp)


def require_managed_source(compiled_pipeline: CompiledPipeline) -> CompiledManagedSource:
    assert isinstance(compiled_pipeline.source, CompiledManagedSource), (
        "Expected compiled pipeline to use a managed Kafka source"
    )
    return compiled_pipeline.source


def build_scalar_target_insert_select_sql(
    *,
    replay_lineage_mode: ReplayLineageMode | str,
    database: str,
    source_table_name: str,
) -> str:
    resolved_replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode)
    return (
        "SELECT CAST(kafka_key AS String) AS order_id, "
        + SCALAR_REPLAY_PROJECTION.get(resolved_replay_lineage_mode, LANDED_AT_REPLAY_PROJECTION)
        + f"FROM {database}.{source_table_name}"
    )


def build_offset_target_insert_select_sql(*, database: str, source_table_name: str) -> str:
    return (
        "SELECT CAST(kafka_key AS String) AS order_id, "
        "CAST(_replay_partition AS Int64) AS _replay_partition, "
        "CAST(_replay_offset AS Int64) AS _replay_offset "
        f"FROM {database}.{source_table_name}"
    )


def build_replay_compiled_pipeline(*, replay_lineage_mode: str) -> CompiledPipeline:
    """Build the compiled pipeline matching a replay lineage mode.

    Offset lineage needs its own fixture; every scalar mode shares one builder
    parameterised by the mode, so callers do not branch on the mode themselves.
    """

    builders: dict[bool, Callable[[], CompiledPipeline]] = {
        True: build_offset_replay_compiled_pipeline,
        False: lambda: build_scalar_replay_compiled_pipeline(replay_lineage_mode),
    }
    return builders[replay_lineage_mode == ReplayLineageMode.OFFSETS]()
