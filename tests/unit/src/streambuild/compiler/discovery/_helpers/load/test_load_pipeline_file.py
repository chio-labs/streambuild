from pathlib import Path

import pytest

from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    LoadedPipeline,
    SchemaChangeBackfillPolicy,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SchemaChangeBackfillMode,
    SourceKind,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load._test_types import (
    LoadPipelineFileAdoptedSourceTestCase,
    LoadPipelineFileErrorTestCase,
    LoadPipelineFileInvalidAdoptedSourceTestCase,
    LoadPipelineFileProjectConfigTestCase,
    LoadPipelineFileRepeatedSourceRefTestCase,
    LoadPipelineFileSchemaChangeBackfillTestCase,
    LoadPipelineFileSqlModelDefaultsTestCase,
    LoadPipelineFileTestCase,
    LoadPipelineFileUnsupportedReplayBehaviorTestCase,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileTestCase(
            description="loads top level pipeline from example file",
            pipeline_file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
            expected_pipeline_name="orders",
            expected_source_name="orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_example_pipeline_file_when_loading_pipeline_then_returns_top_level_pipeline(
    test_case: LoadPipelineFileTestCase,
) -> None:
    loaded: LoadedPipeline = load_pipeline_file(test_case.pipeline_file_path)

    assert loaded.pipeline.name == test_case.expected_pipeline_name
    assert loaded.pipeline.source.name == test_case.expected_source_name
    assert [transform.name for transform in loaded.pipeline.transforms] == ["orders_enriched"]
    assert loaded.pipeline.transforms[0].source == "orders"
    if loaded.project is None:
        assert test_case.expected_project_replay_lineage_mode is None
    else:
        assert loaded.project.replay_lineage_mode == test_case.expected_project_replay_lineage_mode


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileProjectConfigTestCase(
            description="loads project config from project root above pipelines",
            project_file_contents="""
            replay_lineage_mode: timestamp
            default_database: analytics

            clickhouse:
              host: localhost
              port: 8123
              username: streambuild
              password: streambuild
            """,
            pipeline_file_contents="""
            source:
              kind: kafka
              name: orders
              broker_list: kafka:9092
              topic: source.orders
            """,
            expected_pipeline_name="orders",
            expected_project_replay_lineage_mode=ReplayLineageMode.TIMESTAMP,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_file_with_project_config_when_loading_then_it_returns_project_config(
    test_case: LoadPipelineFileProjectConfigTestCase,
    tmp_path: Path,
) -> None:
    project_file_path: Path = tmp_path / "streambuild_project.yml"
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    sql_file_path: Path = tmp_path / "pipelines" / "orders" / "orders_enriched.sql"
    write_pipeline_file(project_file_path, test_case.project_file_contents)
    write_pipeline_file(pipeline_file_path, test_case.pipeline_file_contents)
    write_pipeline_file(
        sql_file_path,
        """
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
    )

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    assert loaded.pipeline.name == test_case.expected_pipeline_name
    assert loaded.project is not None
    assert loaded.project.replay_lineage_mode == test_case.expected_project_replay_lineage_mode
    assert (
        loaded.project.bounded_replay_fallback
        == test_case.expected_project_unsupported_replay_behavior
    )
    assert loaded.project.default_database == "analytics"
    assert loaded.project.clickhouse is not None
    assert loaded.project.clickhouse.host == "localhost"
    assert loaded.project.clickhouse.port == 8123


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileSqlModelDefaultsTestCase(
            description="defaults omitted engine and order by",
            sql_model_contents="""
        MODEL ();

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
            expected_engine="MergeTree()",
            expected_order_by=["_replay_timestamp"],
        ),
        LoadPipelineFileSqlModelDefaultsTestCase(
            description="defaults omitted engine only",
            sql_model_contents="""
        MODEL (
          order_by: ["order_id", "event_at"]
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
            expected_engine="MergeTree()",
            expected_order_by=["order_id", "event_at"],
        ),
        LoadPipelineFileSqlModelDefaultsTestCase(
            description="defaults omitted order by only",
            sql_model_contents="""
        MODEL (
          engine: "ReplacingMergeTree(updated_at)"
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
            expected_engine="ReplacingMergeTree(updated_at)",
            expected_order_by=["_replay_timestamp"],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_with_omitted_storage_fields_when_loading_then_it_applies_defaults(
    test_case: LoadPipelineFileSqlModelDefaultsTestCase,
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
    write_pipeline_file(sql_file_path, test_case.sql_model_contents)

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)
    loaded_transform: TransformStep = loaded.pipeline.transforms[0]

    assert loaded_transform.engine == test_case.expected_engine
    assert loaded_transform.order_by == test_case.expected_order_by


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileAdoptedSourceTestCase(
            description="loads adopted kafka source with replay boundary mapping",
            pipeline_file_contents="""
        source:
          kind: kafka
          name: orders
          table_name: order_events_existing
          replay_boundary:
            mode: offsets
            columns:
              _replay_partition: event_partition
              _replay_offset: event_offset
              _replay_timestamp: event_timestamp
        """,
            expected_source_kind=SourceKind.KAFKA,
            expected_table_name="order_events_existing",
            expected_partition_column="event_partition",
            expected_offset_column="event_offset",
            expected_timestamp_column="event_timestamp",
        ),
        LoadPipelineFileAdoptedSourceTestCase(
            description="loads adopted stream table source with offset replay boundary mapping",
            pipeline_file_contents="""
        source:
          kind: stream_table
          name: orders
          table_name: order_events_existing
          replay_boundary:
            mode: offsets
            columns:
              _replay_partition: event_partition
              _replay_offset: event_offset
              _replay_timestamp: event_timestamp
        """,
            expected_source_kind=SourceKind.STREAM_TABLE,
            expected_table_name="order_events_existing",
            expected_partition_column="event_partition",
            expected_offset_column="event_offset",
            expected_timestamp_column="event_timestamp",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_file_with_adopted_source_when_loading_then_it_parses_external_source(
    test_case: LoadPipelineFileAdoptedSourceTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    sql_file_path: Path = tmp_path / "pipelines" / "orders" / "orders_enriched.sql"
    write_pipeline_file(pipeline_file_path, test_case.pipeline_file_contents)
    write_pipeline_file(
        sql_file_path,
        """
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
    )

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    assert isinstance(loaded.pipeline.source, ExternalTableSourceStep)
    assert loaded.pipeline.source.kind == test_case.expected_source_kind
    assert loaded.pipeline.source.table_name == test_case.expected_table_name
    assert loaded.pipeline.source.replay_boundary.mode == ReplayBoundaryMode.OFFSETS
    assert (
        loaded.pipeline.source.replay_boundary.columns.partition
        == test_case.expected_partition_column
    )
    assert loaded.pipeline.source.replay_boundary.columns.offset == test_case.expected_offset_column
    assert (
        loaded.pipeline.source.replay_boundary.columns.timestamp
        == test_case.expected_timestamp_column
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileSchemaChangeBackfillTestCase(
            description="loads schema change backfill policy from sql model header",
            sql_model_contents="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
          schema_change_backfill: {breaking: bounded(30m), non_breaking: full}
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
            expected_breaking_mode=SchemaChangeBackfillMode.BOUNDED,
            expected_breaking_lookback_seconds=1800,
            expected_non_breaking_mode=SchemaChangeBackfillMode.FULL,
            expected_non_breaking_lookback_seconds=None,
        ),
        LoadPipelineFileSchemaChangeBackfillTestCase(
            description="loads multiline schema change backfill policy from sql model header",
            sql_model_contents="""
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
          schema_change_backfill:
            breaking: bounded(8s)
            non_breaking: bounded(8s),
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
            expected_breaking_mode=SchemaChangeBackfillMode.BOUNDED,
            expected_breaking_lookback_seconds=8,
            expected_non_breaking_mode=SchemaChangeBackfillMode.BOUNDED,
            expected_non_breaking_lookback_seconds=8,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_with_schema_change_backfill_when_loading_then_it_parses_policy(
    test_case: LoadPipelineFileSchemaChangeBackfillTestCase,
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
    write_pipeline_file(sql_file_path, test_case.sql_model_contents)

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)
    schema_change_backfill: SchemaChangeBackfillPolicy | None = loaded.pipeline.transforms[
        0
    ].schema_change_backfill

    assert schema_change_backfill is not None
    assert schema_change_backfill.breaking is not None
    assert schema_change_backfill.breaking.mode == test_case.expected_breaking_mode
    assert (
        schema_change_backfill.breaking.lookback_seconds
        == test_case.expected_breaking_lookback_seconds
    )
    assert schema_change_backfill.non_breaking is not None
    assert schema_change_backfill.non_breaking.mode == test_case.expected_non_breaking_mode
    assert (
        schema_change_backfill.non_breaking.lookback_seconds
        == test_case.expected_non_breaking_lookback_seconds
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileRepeatedSourceRefTestCase(
            description="loads repeated driving source refs as one inferred source",
            sql_model_contents="""
            MODEL (
              engine: "MergeTree()",
              order_by: ["order_id"],
            );

            SELECT left_side.order_id::UInt64 AS order_id
            FROM __ref("orders") AS left_side
            INNER JOIN __ref("orders") AS right_side USING order_id
            """,
            expected_transform_source="orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_model_with_repeated_source_refs_when_loading_then_it_keeps_one_driving_source(
    test_case: LoadPipelineFileRepeatedSourceRefTestCase,
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
    write_pipeline_file(sql_file_path, test_case.sql_model_contents)

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    assert loaded.pipeline.transforms[0].source == test_case.expected_transform_source


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileUnsupportedReplayBehaviorTestCase(
            description="loads unsupported replay behavior from pipeline and model config",
            pipeline_file_contents="""
            source:
              kind: kafka
              name: orders
              broker_list: kafka:9092
              topic: source.orders
            bounded_replay_fallback: bounded_without_history
            """,
            sql_model_contents="""
            MODEL (
              engine: "MergeTree()",
              order_by: ["order_id"],
              bounded_replay_fallback: full_refresh
            );

            SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
            """,
            expected_pipeline_unsupported_replay_behavior=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
            expected_transform_unsupported_replay_behavior=BoundedReplayFallback.FULL_REFRESH,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_and_model_with_unsupported_replay_behavior_when_loading_then_it_parses(
    test_case: LoadPipelineFileUnsupportedReplayBehaviorTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    sql_file_path: Path = tmp_path / "pipelines" / "orders" / "orders_enriched.sql"
    write_pipeline_file(pipeline_file_path, test_case.pipeline_file_contents)
    write_pipeline_file(sql_file_path, test_case.sql_model_contents)

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)

    assert (
        loaded.pipeline.bounded_replay_fallback
        == test_case.expected_pipeline_unsupported_replay_behavior
    )
    assert (
        loaded.pipeline.transforms[0].bounded_replay_fallback
        == test_case.expected_transform_unsupported_replay_behavior
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileErrorTestCase(
            description="raises value error when yaml does not define a top-level mapping",
            file_contents='"missing"',
            expected_error_type=ValueError,
            expected_error_fragment="must define a top-level mapping",
        ),
        LoadPipelineFileErrorTestCase(
            description="raises value error when pipeline yaml defines a redundant name",
            file_contents="""
        name: redundant_name

        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
            expected_error_type=ValueError,
            expected_error_fragment="must not define 'name'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_file_without_pipeline_when_loading_then_it_raises_expected_error(
    test_case: LoadPipelineFileErrorTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "invalid" / "pipeline.yml"
    write_pipeline_file(pipeline_file_path, test_case.file_contents)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        load_pipeline_file(pipeline_file_path)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileErrorTestCase(
            description="raises value error when pipeline file has unsupported source kind",
            file_contents="""
            source:
              kind: postgres
              name: orders
              broker_list: kafka:9092
              topic: source.orders
            """,
            expected_error_type=ValueError,
            expected_error_fragment="currently supports only source.kind='kafka'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_file_with_wrong_pipeline_type_when_loading_then_it_raises_expected_error(
    test_case: LoadPipelineFileErrorTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "invalid" / "pipeline.yml"
    write_pipeline_file(pipeline_file_path, test_case.file_contents)
    write_pipeline_file(
        tmp_path / "pipelines" / "invalid" / "orders_enriched.sql",
        """
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
    )

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        load_pipeline_file(pipeline_file_path)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects qualified adopted source table names",
            pipeline_file_contents="""
        source:
          kind: kafka
          name: orders
          table_name: analytics.orders_existing
          replay_boundary:
            mode: offsets
            columns:
              _replay_partition: event_partition
              _replay_offset: event_offset
              _replay_timestamp: event_timestamp
        """,
            expected_error_fragment="must define source.table_name as a bare table name",
        ),
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects adopted offset sources without required columns",
            pipeline_file_contents="""
        source:
          kind: kafka
          name: orders
          table_name: orders_existing
          replay_boundary:
            mode: offsets
            columns:
              _replay_partition: event_partition
        """,
            expected_error_fragment="must define replay boundary partition and offset columns",
        ),
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects adopted offset sources without a timestamp column",
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
        """,
            expected_error_fragment="must define a replay boundary timestamp column",
        ),
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects adopted offset sources with landed_at column",
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
              _replay_landed_at: event_landed_at
        """,
            expected_error_fragment="must not define a replay boundary landed_at column",
        ),
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects adopted timestamp sources with landed_at column",
            pipeline_file_contents="""
        source:
          kind: kafka
          name: orders
          table_name: orders_existing
          replay_boundary:
            mode: timestamp
            columns:
              _replay_timestamp: event_timestamp
              _replay_landed_at: event_landed_at
        """,
            expected_error_fragment="must not define a replay boundary landed_at column",
        ),
        LoadPipelineFileInvalidAdoptedSourceTestCase(
            description="rejects adopted cursor sources without a timestamp column",
            pipeline_file_contents="""
        source:
          kind: stream_table
          name: orders
          table_name: orders_existing
          replay_boundary:
            mode: cursor
            columns:
              _replay_cursor: event_cursor
        """,
            expected_error_fragment="must define a replay boundary timestamp column",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_adopted_source_when_loading_then_it_raises_expected_error(
    test_case: LoadPipelineFileInvalidAdoptedSourceTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = tmp_path / "pipelines" / "orders" / "pipeline.yml"
    write_pipeline_file(pipeline_file_path, test_case.pipeline_file_contents)
    write_pipeline_file(
        tmp_path / "pipelines" / "orders" / "orders_enriched.sql",
        """
        MODEL (
          engine: "MergeTree()",
          order_by: ["order_id"],
        );

        SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
        """,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        load_pipeline_file(pipeline_file_path)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
