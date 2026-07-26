from dataclasses import replace
from pathlib import Path

import pytest

from streambuild.compiler.compile.exceptions import (
    TransformOrderByUnknownColumnError,
    TransformPartitionByUnknownColumnError,
    TransformSqlTopLevelSetOperationError,
    TransformTtlUnknownColumnError,
)
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledExternalSource,
    CompiledManagedSource,
    CompiledPipeline,
    CompiledTransformStep,
    DesiredState,
)
from streambuild.compiler.desired_state.main import build_desired_state
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.shared.models import DesiredMaterializedView, LoadedPipeline
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.project import Project
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
from tests.unit.src.streambuild.compiler.compile._helpers.builders import (
    build_inline_sql_pipeline,
    build_invalid_order_by_pipeline,
    build_invalid_storage_expression_pipeline,
    build_missing_source_ref_pipeline,
    build_sql_file_pipeline,
)
from tests.unit.src.streambuild.compiler.compile._test_types import (
    CompilePipelineAdditionalRefDependencyTestCase,
    CompilePipelineAdoptedSourceTestCase,
    CompilePipelineInlineRefsTestCase,
    CompilePipelineInlineSqlSuccessTestCase,
    CompilePipelineInvalidOrderByTestCase,
    CompilePipelineInvalidPartitionByTestCase,
    CompilePipelineInvalidTransformSqlTestCase,
    CompilePipelineInvalidTtlTestCase,
    CompilePipelineMissingRefTypeTestCase,
    CompilePipelineMissingSourceRefTestCase,
    CompilePipelineRepeatedSourceRefTestCase,
    CompilePipelineReplayAnchorEligibilityTestCase,
    CompilePipelineReplayLineageModeResolutionTestCase,
    CompilePipelineReplayLineageModeTestCase,
    CompilePipelineReplaySurfaceTestCase,
    CompilePipelineSqlFileTestCase,
    CompilePipelineSqlModelDefaultOrderByTestCase,
    CompilePipelineUnsupportedReplayBehaviorTestCase,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_single_transform_desired_state,
)

REPLAY_LINEAGE_MODE_TEST_CASES: list[CompilePipelineReplayLineageModeTestCase] = [
    CompilePipelineReplayLineageModeTestCase(
        description="uses project replay lineage mode when pipeline does not override it",
        pipeline_replay_lineage_mode=None,
        project_replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        expected_effective_replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
    ),
    CompilePipelineReplayLineageModeTestCase(
        description="pipeline replay lineage mode overrides project default",
        pipeline_replay_lineage_mode=ReplayLineageMode.LANDED_AT,
        project_replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        expected_effective_replay_lineage_mode=ReplayLineageMode.LANDED_AT,
    ),
    CompilePipelineReplayLineageModeTestCase(
        description="falls back to kafka offsets when no project default exists",
        pipeline_replay_lineage_mode=None,
        project_replay_lineage_mode=None,
        expected_effective_replay_lineage_mode=ReplayLineageMode.OFFSETS,
    ),
]

UNSUPPORTED_REPLAY_BEHAVIOR_TEST_CASES: list[CompilePipelineUnsupportedReplayBehaviorTestCase] = [
    CompilePipelineUnsupportedReplayBehaviorTestCase(
        description="uses project unsupported replay behavior when pipeline does not override it",
        transform_unsupported_replay_behavior=None,
        pipeline_unsupported_replay_behavior=None,
        project_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
        expected_effective_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
    ),
    CompilePipelineUnsupportedReplayBehaviorTestCase(
        description="pipeline unsupported replay behavior overrides project default",
        transform_unsupported_replay_behavior=None,
        pipeline_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
        project_unsupported_replay_behavior=BoundedReplayFallback.FULL_REFRESH,
        expected_effective_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
    ),
    CompilePipelineUnsupportedReplayBehaviorTestCase(
        description="transform unsupported replay behavior overrides pipeline and project defaults",
        transform_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
        pipeline_unsupported_replay_behavior=BoundedReplayFallback.FULL_REFRESH,
        project_unsupported_replay_behavior=BoundedReplayFallback.FULL_REFRESH,
        expected_effective_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
    ),
]

REPLAY_ANCHOR_ELIGIBILITY_TEST_CASES: list[CompilePipelineReplayAnchorEligibilityTestCase] = [
    CompilePipelineReplayAnchorEligibilityTestCase(
        description=(
            "marks event-like transform with required offset lineage as replay-anchor-eligible"
        ),
        transform_query=(
            "SELECT CAST(order_id AS UInt64) AS order_id, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders")'
        ),
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        expected_preserves_required_lineage=True,
        expected_replay_anchor_eligible=True,
    ),
    CompilePipelineReplayAnchorEligibilityTestCase(
        description="marks mutable-ref transform as non-anchor-eligible",
        transform_query=(
            "SELECT CAST(order_id AS UInt64) AS order_id, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders") LEFT JOIN '
            '__ref("customers", ref_type="mutable") USING customer_id'
        ),
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        supporting_transforms=(
            (
                "customers",
                'SELECT CAST(customer_id AS UInt64) AS customer_id FROM __ref("orders")',
            ),
        ),
        expected_has_mutable_refs=True,
        expected_preserves_required_lineage=True,
        expected_replay_anchor_eligible=False,
    ),
    CompilePipelineReplayAnchorEligibilityTestCase(
        description="marks grouped transform as non-anchor-eligible",
        transform_query=(
            "SELECT CAST(customer_id AS UInt64) AS customer_id, "
            "CAST(count() AS UInt64) AS order_count, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders") GROUP BY customer_id, _replay_partition, _replay_offset'
        ),
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        order_by=("customer_id",),
        expected_has_aggregate_semantics=True,
        expected_preserves_required_lineage=True,
        expected_replay_anchor_eligible=False,
    ),
    CompilePipelineReplayAnchorEligibilityTestCase(
        description="marks transform missing required lineage as non-anchor-eligible",
        transform_query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")',
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        expected_preserves_required_lineage=False,
        expected_replay_anchor_eligible=False,
    ),
    CompilePipelineReplayAnchorEligibilityTestCase(
        description="respects explicit replay-anchor veto",
        transform_query=(
            "SELECT CAST(order_id AS UInt64) AS order_id, "
            "CAST(_replay_partition AS UInt64) AS _replay_partition, "
            "CAST(_replay_offset AS UInt64) AS _replay_offset "
            'FROM __ref("orders")'
        ),
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        replay_anchor=ReplayAnchorMode.NEVER,
        expected_preserves_required_lineage=True,
        expected_replay_anchor_eligible=False,
    ),
]

REPLAY_SURFACE_TEST_CASES: list[CompilePipelineReplaySurfaceTestCase] = [
    CompilePipelineReplaySurfaceTestCase(
        description="managed kafka landing exposes replay lineage columns to transforms",
        pipeline=Pipeline(
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
                TransformStep(
                    name="orders_enriched",
                    source="orders",
                    engine="MergeTree()",
                    order_by=["order_id"],
                    query=(
                        "SELECT CAST(order_id AS UInt64) AS order_id, "
                        "CAST(_replay_landed_at AS DateTime64(3)) AS _replay_landed_at "
                        'FROM __ref("orders")'
                    ),
                )
            ],
            replay_lineage_mode=ReplayLineageMode.LANDED_AT,
        ),
        expected_query_fragments=("_replay_landed_at",),
        expected_output_column_names=("order_id", "_replay_landed_at"),
    ),
    CompilePipelineReplaySurfaceTestCase(
        description="adopted external sources expose replay lineage columns to transforms",
        pipeline=Pipeline(
            name="tmp_pipeline",
            source=ExternalTableSourceStep(
                name="orders",
                kind=SourceKind.KAFKA,
                table_name="orders_existing",
                replay_boundary=ReplayBoundary(
                    mode=ReplayBoundaryMode.TIMESTAMP,
                    columns=ReplayBoundaryColumns(timestamp="event_timestamp"),
                ),
            ),
            transforms=[
                TransformStep(
                    name="orders_enriched",
                    source="orders",
                    engine="MergeTree()",
                    order_by=["order_id"],
                    query=(
                        "SELECT CAST(order_id AS UInt64) AS order_id, "
                        "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
                        'FROM __ref("orders")'
                    ),
                )
            ],
            replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        ),
        expected_query_fragments=("_replay_timestamp", "event_timestamp"),
        expected_output_column_names=("order_id", "_replay_timestamp"),
    ),
    CompilePipelineReplaySurfaceTestCase(
        description="adopted cursor sources expose replay cursor columns to transforms",
        pipeline=Pipeline(
            name="tmp_pipeline",
            source=ExternalTableSourceStep(
                name="orders",
                kind=SourceKind.STREAM_TABLE,
                table_name="orders_existing",
                replay_boundary=ReplayBoundary(
                    mode=ReplayBoundaryMode.CURSOR,
                    columns=ReplayBoundaryColumns(cursor="event_cursor"),
                ),
            ),
            transforms=[
                TransformStep(
                    name="orders_enriched",
                    source="orders",
                    engine="MergeTree()",
                    order_by=["order_id"],
                    query=(
                        "SELECT CAST(order_id AS UInt64) AS order_id, "
                        "CAST(_replay_cursor AS UInt64) AS _replay_cursor "
                        'FROM __ref("orders")'
                    ),
                )
            ],
            replay_lineage_mode=ReplayLineageMode.CURSOR,
        ),
        expected_query_fragments=("_replay_cursor", "event_cursor"),
        expected_output_column_names=("order_id", "_replay_cursor"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInlineRefsTestCase(
            description="resolves inline refs for example pipeline",
            pipeline_file_path="tests/fixtures/basic_project/pipelines/orders/pipeline.yml",
            expected_relation_names={
                "orders": "raw__orders",
                "orders_enriched": "tbl__orders_enriched",
            },
            expected_kafka_table_name="kafka__orders",
            expected_raw_table_name="raw__orders",
            expected_landing_mv_name="mv__orders",
            expected_landing_query_fragments=(
                "_key AS kafka_key",
                "message AS kafka_value",
                "_topic AS kafka_topic",
                "_partition AS _replay_partition",
                "_offset AS _replay_offset",
                "_timestamp AS _replay_timestamp",
                "_partition AS _replay_partition",
                "_offset AS _replay_offset",
                "_timestamp AS _replay_timestamp",
                "now64(3) AS _replay_landed_at",
                "now64(3) AS _replay_landed_at",
                "FROM kafka__orders",
            ),
            expected_refs=("orders",),
            expected_query_fragment="FROM raw__orders",
            expected_target_table_name="tbl__orders_enriched",
            expected_transform_mv_name="mv__orders_enriched",
            expected_desired_state_ordered_keys=(
                (None, "kafka_table", "kafka__orders"),
                (None, "materialized_view", "mv__orders"),
                (None, "materialized_view", "mv__orders_enriched"),
                (None, "table", "raw__orders"),
                (None, "table", "tbl__orders_enriched"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_example_pipeline_when_compiling_then_resolves_inline_refs(
    test_case: CompilePipelineInlineRefsTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = load_pipeline_file(Path(test_case.pipeline_file_path))
    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)
    assert isinstance(compiled_pipeline.source, CompiledManagedSource)
    managed_source: CompiledManagedSource = compiled_pipeline.source

    assert compiled_pipeline.relation_names == test_case.expected_relation_names
    assert managed_source.kafka_table.name == test_case.expected_kafka_table_name
    assert managed_source.raw_table.name == test_case.expected_raw_table_name
    assert managed_source.materialized_view.name == test_case.expected_landing_mv_name
    assert managed_source.materialized_view.source_table_name == test_case.expected_kafka_table_name
    assert managed_source.materialized_view.target_table_name == test_case.expected_raw_table_name
    for expected_fragment in test_case.expected_landing_query_fragments:
        assert expected_fragment in managed_source.materialized_view.query
    assert compiled_pipeline.transforms[0].refs == test_case.expected_refs
    assert test_case.expected_query_fragment in compiled_pipeline.transforms[0].resolved_query
    assert compiled_pipeline.transforms[0].target_table_name == test_case.expected_target_table_name
    assert compiled_pipeline.transforms[0].target_table.name == test_case.expected_target_table_name
    assert (
        compiled_pipeline.transforms[0].materialized_view.name
        == test_case.expected_transform_mv_name
    )
    assert (
        compiled_pipeline.transforms[0].materialized_view.source_table_name
        == test_case.expected_raw_table_name
    )
    assert (
        compiled_pipeline.transforms[0].materialized_view.target_table_name
        == test_case.expected_target_table_name
    )
    assert tuple(
        (dependency.database, dependency.object_type, dependency.name)
        for dependency in compiled_pipeline.transforms[0].target_table.deps
    ) == ((None, "table", "raw__orders"),)
    assert tuple(
        (dependency.database, dependency.object_type, dependency.name)
        for dependency in compiled_pipeline.transforms[0].materialized_view.deps
    ) == (
        (None, "table", "raw__orders"),
        (None, "table", "tbl__orders_enriched"),
    )
    assert tuple(
        column.name for column in compiled_pipeline.transforms[0].target_table.columns
    ) == (
        "order_id",
        "customer_id",
        "order_total",
        "created_at",
        "updated_at",
        "_replay_landed_at",
    )

    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    assert (
        tuple(
            (object_.key.database, object_.key.object_type, object_.key.name)
            for object_ in desired_state.objects
        )
        == test_case.expected_desired_state_ordered_keys
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineAdoptedSourceTestCase(
            description="compiles adopted source against its existing table name",
            pipeline_file_contents="""
source:
  kind: kafka
  name: orders
  table_name: orders_existing
  replay_boundary:
    mode: offsets
    columns:
      _replay_partition: event_partition
      _replay_offset: event_offset
      _replay_timestamp: event_timestamp
""",
            sql_contents="""
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT
  CAST(order_id AS UInt64) AS order_id,
  CAST(event_partition AS UInt64) AS _replay_partition,
  CAST(event_offset AS UInt64) AS _replay_offset
FROM __ref("orders")
""",
            expected_source_relation_name="orders_existing",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adopted_source_when_compiling_then_it_uses_existing_table_relation_name(
    test_case: CompilePipelineAdoptedSourceTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    sql_file_path: Path = tmp_path / "pipelines" / "orders" / "orders_enriched.sql"
    pipeline_file_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_file_path.write_text(
        test_case.pipeline_file_contents.strip() + "\n",
        encoding="utf-8",
    )
    sql_file_path.write_text(
        test_case.sql_contents.strip() + "\n",
        encoding="utf-8",
    )

    loaded_pipeline: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)

    assert isinstance(compiled_pipeline.source, CompiledExternalSource)
    assert compiled_pipeline.relation_names == {
        "orders": test_case.expected_source_relation_name,
        "orders_enriched": "tbl__orders_enriched",
    }
    assert (
        f"FROM {test_case.expected_source_relation_name}"
        in compiled_pipeline.transforms[0].resolved_query
    )

    desired_state: DesiredState = build_desired_state((compiled_pipeline,))

    assert tuple(object_.key.name for object_ in desired_state.objects) == (
        "mv__orders_enriched",
        "tbl__orders_enriched",
    )
    assert tuple(config.table_name for config in desired_state.external_source_replay_configs) == (
        test_case.expected_source_relation_name,
    )
    assert any(
        key.name == test_case.expected_source_relation_name
        for key in desired_state.replay_anchor_keys
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInlineSqlSuccessTestCase(
            description="compiles clickhouse double-colon casts in transform sql",
            transform_query='SELECT order_id::UInt64 AS order_id FROM __ref("orders")',
            expected_output_columns=(("order_id", "UInt64"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_inline_transform_sql_when_compiling_then_it_derives_expected_columns(
    test_case: CompilePipelineInlineSqlSuccessTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_inline_sql_pipeline(test_case.transform_query)

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)

    assert (
        tuple(
            (column.name, column.type)
            for column in compiled_pipeline.transforms[0].target_table.columns
        )
        == test_case.expected_output_columns
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineSqlFileTestCase(
            description="loads sql file relative to pipeline file",
            sql_relative_path="sql/prices.sql",
            sql_contents='SELECT CAST(kafka_value AS UInt64) AS order_id FROM __ref("orders")',
            expected_resolved_query=(
                "SELECT CAST(kafka_value AS UInt64) AS order_id FROM raw__orders"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_transform_sql_file_when_compiling_then_loads_sql_relative_to_pipeline_file(
    test_case: CompilePipelineSqlFileTestCase,
    tmp_path: Path,
) -> None:
    loaded_pipeline: LoadedPipeline = build_sql_file_pipeline(
        tmp_path,
        test_case.sql_relative_path,
        test_case.sql_contents,
    )

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)

    assert compiled_pipeline.transforms[0].resolved_query == test_case.expected_resolved_query


@pytest.mark.parametrize(
    "test_case",
    REPLAY_LINEAGE_MODE_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_loaded_pipeline_when_compiling_then_it_resolves_effective_replay_lineage_mode(
    test_case: CompilePipelineReplayLineageModeTestCase,
) -> None:
    base_loaded_pipeline: LoadedPipeline = build_inline_sql_pipeline(
        transform_query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")'
    )
    pipeline: Pipeline = replace(
        base_loaded_pipeline.pipeline,
        replay_lineage_mode=test_case.pipeline_replay_lineage_mode,
    )
    project: Project | None = None
    if test_case.project_replay_lineage_mode is not None:
        project = Project(replay_lineage_mode=test_case.project_replay_lineage_mode)
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=base_loaded_pipeline.file_path,
        project=project,
    )

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)

    assert (
        compiled_pipeline.effective_replay_lineage_mode
        == test_case.expected_effective_replay_lineage_mode
    )


@pytest.mark.parametrize(
    "test_case",
    UNSUPPORTED_REPLAY_BEHAVIOR_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_loaded_pipeline_when_compiling_then_it_resolves_effective_unsupported_behavior(
    test_case: CompilePipelineUnsupportedReplayBehaviorTestCase,
) -> None:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(broker_list="kafka:9092", topic="source.orders.created"),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query='SELECT CAST(kafka_key AS String) AS order_id FROM __ref("orders")',
                bounded_replay_fallback=test_case.transform_unsupported_replay_behavior,
            )
        ],
        bounded_replay_fallback=test_case.pipeline_unsupported_replay_behavior,
    )
    project: Project | None = None
    if test_case.project_unsupported_replay_behavior is not None:
        project = Project(bounded_replay_fallback=test_case.project_unsupported_replay_behavior)

    compiled_pipeline: CompiledPipeline = compile_pipeline(
        LoadedPipeline(pipeline=pipeline, file_path=Path("pipeline.yml"), project=project)
    )

    assert (
        compiled_pipeline.transforms[0].effective_bounded_replay_fallback
        == test_case.expected_effective_unsupported_replay_behavior
    )
    assert (
        compiled_pipeline.transforms[0].target_table.bounded_replay_fallback
        == test_case.expected_effective_unsupported_replay_behavior
    )


@pytest.mark.parametrize(
    "test_case",
    REPLAY_ANCHOR_ELIGIBILITY_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_transform_when_compiling_then_it_sets_replay_anchor_inference_flags(
    test_case: CompilePipelineReplayAnchorEligibilityTestCase,
) -> None:
    source: KafkaLandingStep = KafkaLandingStep(
        name="orders",
        kafka=KafkaSettings(
            broker_list="kafka:9092",
            topic="source.orders",
            consumer_group="streambuild_tmp_pipeline_orders",
        ),
    )
    supporting_transforms: list[TransformStep] = [
        TransformStep(
            name=name,
            source="orders",
            engine="MergeTree()",
            order_by=["customer_id"],
            query=query,
        )
        for name, query in test_case.supporting_transforms
    ]
    transform: TransformStep = TransformStep(
        name="orders_enriched",
        source="orders",
        engine=test_case.engine,
        order_by=list(test_case.order_by),
        query=test_case.transform_query,
        replay_anchor=test_case.replay_anchor,
    )
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=source,
        transforms=[*supporting_transforms, transform],
        replay_lineage_mode=test_case.replay_lineage_mode,
    )
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
        project=None,
    )

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)
    compiled_transform: CompiledTransformStep = compiled_pipeline.transforms[-1]

    assert compiled_transform.has_mutable_refs is test_case.expected_has_mutable_refs
    assert compiled_transform.has_aggregate_semantics is test_case.expected_has_aggregate_semantics
    assert (
        compiled_transform.preserves_required_lineage
        is test_case.expected_preserves_required_lineage
    )
    assert compiled_transform.replay_anchor_eligible is test_case.expected_replay_anchor_eligible


@pytest.mark.parametrize(
    "test_case",
    REPLAY_SURFACE_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_pipeline_when_compiling_then_it_exposes_the_replay_surface(
    test_case: CompilePipelineReplaySurfaceTestCase,
) -> None:
    compiled_pipeline: CompiledPipeline = compile_pipeline(
        LoadedPipeline(
            pipeline=test_case.pipeline,
            file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
            project=None,
        )
    )

    expected_query_fragment: str
    for expected_query_fragment in test_case.expected_query_fragments:
        assert expected_query_fragment in compiled_pipeline.transforms[0].resolved_query
    assert (
        tuple(column.name for column in compiled_pipeline.transforms[0].target_table.columns)
        == test_case.expected_output_column_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineReplayLineageModeResolutionTestCase(
            description="cursor external source resolves cursor replay lineage mode",
            pipeline=Pipeline(
                name="tmp_pipeline",
                source=ExternalTableSourceStep(
                    name="orders",
                    kind=SourceKind.STREAM_TABLE,
                    table_name="orders_existing",
                    replay_boundary=ReplayBoundary(
                        mode=ReplayBoundaryMode.CURSOR,
                        columns=ReplayBoundaryColumns(cursor="event_cursor"),
                    ),
                ),
                transforms=[
                    TransformStep(
                        name="orders_enriched",
                        source="orders",
                        engine="MergeTree()",
                        order_by=["order_id"],
                        query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")',
                    )
                ],
            ),
            expected_replay_lineage_mode=ReplayLineageMode.CURSOR,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_when_compiling_then_it_resolves_expected_replay_lineage_mode(
    test_case: CompilePipelineReplayLineageModeResolutionTestCase,
) -> None:
    compiled_pipeline: CompiledPipeline = compile_pipeline(
        LoadedPipeline(
            pipeline=test_case.pipeline,
            file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
            project=None,
        )
    )

    assert compiled_pipeline.effective_replay_lineage_mode == test_case.expected_replay_lineage_mode


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineMissingSourceRefTestCase(
            description="raises value error when transform sql omits source ref",
            transform_query="SELECT CAST(order_id AS String) AS order_id FROM tbl__other",
            expected_error_type=ValueError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_transform_without_source_ref_when_compiling_then_raises_value_error(
    test_case: CompilePipelineMissingSourceRefTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_missing_source_ref_pipeline(test_case.transform_query)

    with pytest.raises(test_case.expected_error_type):
        compile_pipeline(loaded_pipeline)


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineMissingRefTypeTestCase(
            description="raises value error when additional ref omits ref_type",
            transform_query=(
                'SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders") '
                'LEFT JOIN __ref("customers") USING customer_id'
            ),
            expected_error_type=ValueError,
            expected_error_fragment="must declare ref_type for additional ref 'customers'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_additional_ref_without_ref_type_when_compiling_then_it_raises_value_error(
    test_case: CompilePipelineMissingRefTypeTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_inline_sql_pipeline(test_case.transform_query)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        compile_pipeline(loaded_pipeline)


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineRepeatedSourceRefTestCase(
            description="compiles repeated driving source refs without ref_type annotations",
            transform_query=(
                "SELECT left_side.order_id::UInt64 AS order_id "
                'FROM __ref("orders") AS left_side '
                'INNER JOIN __ref("orders") AS right_side USING order_id'
            ),
            expected_target_name="orders_enriched",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_driving_source_refs_when_compiling_then_it_treats_them_as_one_source(
    test_case: CompilePipelineRepeatedSourceRefTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_inline_sql_pipeline(test_case.transform_query)

    compiled_pipeline: CompiledPipeline = compile_pipeline(loaded_pipeline)

    assert compiled_pipeline.transforms[0].transform.name == test_case.expected_target_name


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInvalidTransformSqlTestCase(
            description="raises a clear custom error for top level union output",
            transform_query="""
                SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
                UNION ALL
                SELECT CAST(order_id AS UInt64) AS order_id FROM replay_orders
            """,
            expected_error_type=TransformSqlTopLevelSetOperationError,
            expected_message_fragments=(
                "outermost SELECT",
                "UNION or UNION ALL",
                "expr::Type AS name",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_inline_transform_sql_when_compiling_then_it_raises_a_clear_contract_error(
    test_case: CompilePipelineInvalidTransformSqlTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_inline_sql_pipeline(test_case.transform_query)

    with pytest.raises(test_case.expected_error_type) as error_info:
        compile_pipeline(loaded_pipeline)

    error_message: str = str(error_info.value)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInvalidOrderByTestCase(
            description=(
                "raises a clear custom error for order by expressions "
                "that reference missing columns"
            ),
            transform_query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")',
            order_by=("toYYYYMM(created_at)",),
            expected_error_type=TransformOrderByUnknownColumnError,
            expected_message_fragments=(
                "invalid ORDER BY expression",
                "created_at",
                "Available columns: order_id",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_transform_order_by_when_compiling_then_it_raises_a_clear_contract_error(
    test_case: CompilePipelineInvalidOrderByTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_invalid_order_by_pipeline(
        test_case.transform_query,
        list(test_case.order_by),
    )

    with pytest.raises(test_case.expected_error_type) as error_info:
        compile_pipeline(loaded_pipeline)

    error_message: str = str(error_info.value)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineAdditionalRefDependencyTestCase(
            description="tracks additional reference tables as materialized view dependencies",
            query=(
                "SELECT CAST(order_id AS UInt64) AS order_id, "
                "CAST(_replay_partition AS UInt64) AS _replay_partition, "
                "CAST(_replay_offset AS UInt64) AS _replay_offset "
                'FROM __ref("orders") LEFT JOIN __ref("customers", ref_type="reference") '
                "USING customer_id"
            ),
            expected_materialized_view_deps=(
                "raw__orders",
                "tbl__customers",
                "tbl__orders_enriched",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_additional_ref_when_compiling_then_materialized_view_depends_on_the_reference_table(
    test_case: CompilePipelineAdditionalRefDependencyTestCase,
) -> None:
    desired_state: DesiredState = build_single_transform_desired_state(
        query=test_case.query,
        supporting_transforms=(
            (
                "customers",
                'SELECT CAST(customer_id AS UInt64) AS customer_id FROM __ref("orders")',
                ("customer_id",),
            ),
        ),
    )
    orders_enriched_mv: DesiredMaterializedView = next(
        object_
        for object_ in desired_state.objects
        if isinstance(object_, DesiredMaterializedView) and object_.name == "mv__orders_enriched"
    )

    assert tuple(dependency.name for dependency in orders_enriched_mv.deps) == (
        test_case.expected_materialized_view_deps
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineSqlModelDefaultOrderByTestCase(
            description=(
                "raises a clear order by error when the default replay timestamp key is missing"
            ),
            sql_contents="""
            MODEL ();

            SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
            """,
            expected_error_type=TransformOrderByUnknownColumnError,
            expected_message_fragments=(
                "invalid ORDER BY expression",
                "_replay_timestamp",
                "Available columns: order_id",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_without_replay_timestamp_when_compiling_then_it_raises_order_by_error(
    test_case: CompilePipelineSqlModelDefaultOrderByTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    sql_file_path: Path = tmp_path / "pipelines" / "orders" / "orders_enriched.sql"
    write_pipeline_file(
        pipeline_file_path,
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(sql_file_path, test_case.sql_contents)
    loaded_pipeline: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    with pytest.raises(test_case.expected_error_type) as error_info:
        compile_pipeline(loaded_pipeline)

    error_message: str = str(error_info.value)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInvalidPartitionByTestCase(
            description=(
                "raises a clear custom error for partition by expressions "
                "that reference missing columns"
            ),
            transform_query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")',
            partition_by="toYYYYMM(created_at)",
            expected_error_type=TransformPartitionByUnknownColumnError,
            expected_message_fragments=(
                "invalid PARTITION BY expression",
                "created_at",
                "Available columns: order_id",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_transform_partition_by_when_compiling_then_it_raises_a_clear_contract_error(
    test_case: CompilePipelineInvalidPartitionByTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_invalid_storage_expression_pipeline(
        transform_query=test_case.transform_query,
        order_by=["order_id"],
        partition_by=test_case.partition_by,
    )

    with pytest.raises(test_case.expected_error_type) as error_info:
        compile_pipeline(loaded_pipeline)

    error_message: str = str(error_info.value)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePipelineInvalidTtlTestCase(
            description=(
                "raises a clear custom error for ttl expressions that reference missing columns"
            ),
            transform_query='SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")',
            ttl="toDateTime(created_at) + INTERVAL 30 DAY",
            expected_error_type=TransformTtlUnknownColumnError,
            expected_message_fragments=(
                "invalid TTL expression",
                "created_at",
                "Available columns: order_id",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_transform_ttl_when_compiling_then_it_raises_a_clear_contract_error(
    test_case: CompilePipelineInvalidTtlTestCase,
) -> None:
    loaded_pipeline: LoadedPipeline = build_invalid_storage_expression_pipeline(
        transform_query=test_case.transform_query,
        order_by=["order_id"],
        ttl=test_case.ttl,
    )

    with pytest.raises(test_case.expected_error_type) as error_info:
        compile_pipeline(loaded_pipeline)

    error_message: str = str(error_info.value)
    for expected_fragment in test_case.expected_message_fragments:
        assert expected_fragment in error_message


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
