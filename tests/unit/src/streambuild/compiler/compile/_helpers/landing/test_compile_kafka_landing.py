import pytest

from streambuild.compiler.compile._helpers.landing import compile_kafka_landing
from streambuild.compiler.compile.models import CompiledManagedSource
from streambuild.compiler.discovery.models import Pipeline
from tests.unit.src.streambuild.compiler.compile._helpers.landing._test_types import (
    CompileKafkaLandingErrorTestCase,
    CompileKafkaLandingTestCase,
)
from tests.unit.src.streambuild.compiler.compile._helpers.landing.helpers import build_pipeline


@pytest.mark.parametrize(
    "test_case",
    [
        CompileKafkaLandingTestCase(
            description="compiles kafka landing with default consumer group",
            expected_kafka_table_name="kafka__orders",
            expected_kafka_table_key=(None, "kafka_table", "kafka__orders"),
            expected_kafka_column_names=("message",),
            expected_kafka_broker_list="kafka:9092",
            expected_topic="source.orders.created",
            expected_consumer_group="streambuild_orders_orders",
            expected_format="JSONAsString",
            expected_kafka_extra_settings=None,
            expected_raw_table_name="raw__orders",
            expected_raw_table_key=(None, "table", "raw__orders"),
            expected_raw_column_names=(
                "kafka_key",
                "kafka_value",
                "kafka_topic",
                "kafka_partition",
                "kafka_offset",
                "kafka_timestamp",
                "_replay_partition",
                "_replay_offset",
                "_replay_timestamp",
                "kafka_headers",
                "kafka_landed_at",
                "_replay_landed_at",
            ),
            expected_raw_engine="MergeTree()",
            expected_raw_order_by=("_replay_partition", "_replay_offset"),
            expected_mv_name="mv__orders",
            expected_mv_key=(None, "materialized_view", "mv__orders"),
            expected_mv_dep_keys=(
                (None, "kafka_table", "kafka__orders"),
                (None, "table", "raw__orders"),
            ),
            expected_mv_source_table_name="kafka__orders",
            expected_mv_target_table_name="raw__orders",
            expected_mv_query_fragments=(
                "_key AS kafka_key",
                "message AS kafka_value",
                "_topic AS kafka_topic",
                "_partition AS _replay_partition",
                "_offset AS _replay_offset",
                "_timestamp AS _replay_timestamp",
                "'' AS kafka_headers",
                "now64(3) AS kafka_landed_at",
                "now64(3) AS _replay_landed_at",
                "FROM kafka__orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_when_compiling_kafka_landing_then_it_returns_expected_desired_objects(
    test_case: CompileKafkaLandingTestCase,
) -> None:
    compiled_landing: CompiledManagedSource = compile_kafka_landing(build_pipeline())

    assert compiled_landing.kafka_table.name == test_case.expected_kafka_table_name
    assert (
        compiled_landing.kafka_table.key.database,
        compiled_landing.kafka_table.key.object_type,
        compiled_landing.kafka_table.key.name,
    ) == test_case.expected_kafka_table_key
    assert compiled_landing.kafka_table.deps == ()
    assert tuple(column.name for column in compiled_landing.kafka_table.columns) == (
        test_case.expected_kafka_column_names
    )
    assert compiled_landing.kafka_table.kafka.broker_list == test_case.expected_kafka_broker_list
    assert compiled_landing.kafka_table.kafka.topic == test_case.expected_topic
    assert compiled_landing.kafka_table.kafka.consumer_group == test_case.expected_consumer_group
    assert compiled_landing.kafka_table.kafka.format == test_case.expected_format
    assert compiled_landing.kafka_table.kafka.settings == test_case.expected_kafka_extra_settings
    assert compiled_landing.raw_table.name == test_case.expected_raw_table_name
    assert (
        compiled_landing.raw_table.key.database,
        compiled_landing.raw_table.key.object_type,
        compiled_landing.raw_table.key.name,
    ) == test_case.expected_raw_table_key
    assert compiled_landing.raw_table.deps == ()
    assert tuple(column.name for column in compiled_landing.raw_table.columns) == (
        test_case.expected_raw_column_names
    )
    assert compiled_landing.raw_table.engine == test_case.expected_raw_engine
    assert compiled_landing.raw_table.order_by == test_case.expected_raw_order_by
    assert compiled_landing.materialized_view.name == test_case.expected_mv_name
    assert (
        compiled_landing.materialized_view.key.database,
        compiled_landing.materialized_view.key.object_type,
        compiled_landing.materialized_view.key.name,
    ) == test_case.expected_mv_key
    assert (
        tuple(
            (dependency.database, dependency.object_type, dependency.name)
            for dependency in compiled_landing.materialized_view.deps
        )
        == test_case.expected_mv_dep_keys
    )
    assert (
        compiled_landing.materialized_view.source_table_name
        == test_case.expected_mv_source_table_name
    )
    assert (
        compiled_landing.materialized_view.target_table_name
        == test_case.expected_mv_target_table_name
    )
    for expected_fragment in test_case.expected_mv_query_fragments:
        assert expected_fragment in compiled_landing.materialized_view.query


@pytest.mark.parametrize(
    "test_case",
    [
        CompileKafkaLandingErrorTestCase(
            description="raises for unsupported kafka source formats during compile",
            source_format="JSONEachRow",
            consumer_group=None,
            settings=None,
            expected_error_type=ValueError,
            expected_error_fragment="supports only the 'JSONAsString' format",
        ),
        CompileKafkaLandingErrorTestCase(
            description="raises when escape hatch settings redefine typed kafka settings",
            source_format=None,
            consumer_group=None,
            settings={"kafka_group_name": "duplicate_override"},
            expected_error_type=ValueError,
            expected_error_fragment="cannot redefine typed Kafka settings",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_kafka_source_format_when_compiling_then_it_raises_value_error(
    test_case: CompileKafkaLandingErrorTestCase,
) -> None:
    pipeline: Pipeline = build_pipeline(
        source_format=test_case.source_format or "JSONAsString",
        consumer_group=test_case.consumer_group,
        settings=test_case.settings,
    )

    with pytest.raises(test_case.expected_error_type) as exception_info:
        compile_kafka_landing(pipeline)

    assert test_case.expected_error_fragment in str(exception_info.value)
