import pytest

from streambuild.compiler.actual_state.main._build_actual_state import build_actual_state
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
)
from tests.unit.src.streambuild.compiler.actual_state._test_types import (
    BuildActualStateTestCase,
)
from tests.unit.src.streambuild.compiler.actual_state.helpers import build_actual_objects


@pytest.mark.parametrize(
    "test_case",
    [
        BuildActualStateTestCase(
            description="builds deterministically ordered actual state from shared specs",
            expected_ordered_keys=(
                (None, "kafka_table", "kafka__orders"),
                (None, "materialized_view", "mv__orders_enriched"),
                (None, "table", "tbl__orders_enriched"),
            ),
            expected_first_table_settings={"index_granularity": "8192"},
            expected_first_mv_source_table_name="raw__orders",
            expected_first_kafka_consumer_group="streambuild_orders_orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsorted_actual_objects_when_building_actual_state_then_it_returns_expected_state(
    test_case: BuildActualStateTestCase,
) -> None:
    actual_state: ActualState = build_actual_state(build_actual_objects())
    kafka_table: ActualKafkaTable | ActualTable | ActualMaterializedView = actual_state.objects[0]
    materialized_view: ActualKafkaTable | ActualTable | ActualMaterializedView = (
        actual_state.objects[1]
    )
    table: ActualKafkaTable | ActualTable | ActualMaterializedView = actual_state.objects[2]
    assert isinstance(kafka_table, ActualKafkaTable)
    assert isinstance(materialized_view, ActualMaterializedView)
    assert isinstance(table, ActualTable)

    assert (
        tuple(
            (object_.key.database, object_.key.object_type, object_.key.name)
            for object_ in actual_state.objects
        )
        == test_case.expected_ordered_keys
    )
    assert kafka_table.kafka.consumer_group == test_case.expected_first_kafka_consumer_group
    assert materialized_view.source_table_name == test_case.expected_first_mv_source_table_name
    assert table.settings == test_case.expected_first_table_settings
