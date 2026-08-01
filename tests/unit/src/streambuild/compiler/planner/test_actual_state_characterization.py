from collections.abc import Mapping
from typing import cast

import pytest

from streambuild.adapter.models import (
    AdapterIdentity,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.compiler.compile.models import DesiredState, TableSpec
from streambuild.compiler.planner._helpers.actual_state import build_inspected_actual_objects
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    active_table_specs_from_catalog as _active_table_specs_from_catalog,
)
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    decode_table_column_system_row as _decode_table_column_system_row,
)
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    decode_table_storage_system_row as _decode_table_storage_system_row,
)
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    normalize_storage_engine as _normalize_storage_engine,
)
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    parse_sorting_key as _parse_sorting_key,
)
from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualStateInspection,
    ActualTable,
    ActualView,
    TableColumnSystemRow,
    TableStorageSystemRow,
)
from tests.unit.src.streambuild.compiler.planner._test_types import (
    ActualStateProjectionTestCase,
    ActualStateRowNormalizationTestCase,
    PreservedCatalogProjectionTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_projection_characterization_inputs,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PreservedCatalogProjectionTestCase(
            description="keeps newly inspected TTL and settings outside comparable actual state",
            expected_ttl=None,
            expected_settings=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rich_catalog_when_projecting_actual_state_then_known_options_stay_unloaded(
    test_case: PreservedCatalogProjectionTestCase,
) -> None:
    catalog: CatalogSnapshot = CatalogSnapshot(
        identity=CatalogIdentity(
            adapter=AdapterIdentity(name="clickhouse"),
            database="analytics",
        ),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="tbl__orders__dep_a",
                engine="MergeTree",
                columns=(CatalogColumn(name="order_id", type="String"),),
                order_by=("order_id",),
                ttl="created_at + INTERVAL 30 DAY",
                settings=(("index_granularity", "8192"),),
            ),
        ),
    )

    table_specs: dict[str, TableSpec] = _active_table_specs_from_catalog(
        catalog=catalog,
        database="analytics",
        table_names=("tbl__orders__dep_a",),
    )
    table_spec: TableSpec = table_specs["tbl__orders__dep_a"]

    assert table_spec.storage.ttl == test_case.expected_ttl
    assert table_spec.storage.settings == test_case.expected_settings


@pytest.mark.parametrize(
    "test_case",
    [
        ActualStateRowNormalizationTestCase(
            description="normalizes ClickHouse system rows into the current comparable shape",
            raw_engine="MergeTree",
            raw_sorting_key="(order_id, updated_at)",
            raw_default_expression="",
            raw_partition_key="tuple()",
            expected_engine="MergeTree()",
            expected_order_by=("order_id", "updated_at"),
            expected_default_expression=None,
            expected_partition_key=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_system_rows_when_normalizing_then_returns_current_comparable_values(
    test_case: ActualStateRowNormalizationTestCase,
) -> None:
    column_row: TableColumnSystemRow = _decode_table_column_system_row(
        cast(
            Mapping[str, object],
            {
                "table": "tbl__orders_enriched__dep_a",
                "name": "updated_at",
                "type": "DateTime64(3)",
                "default_expression": test_case.raw_default_expression,
            },
        )
    )
    storage_row: TableStorageSystemRow = _decode_table_storage_system_row(
        cast(
            Mapping[str, object],
            {
                "name": "tbl__orders_enriched__dep_a",
                "engine": test_case.raw_engine,
                "sorting_key": test_case.raw_sorting_key,
                "partition_key": test_case.raw_partition_key,
            },
        )
    )

    assert _normalize_storage_engine(storage_row.engine) == test_case.expected_engine
    assert _parse_sorting_key(storage_row.sorting_key) == test_case.expected_order_by
    assert column_row.default_expression == test_case.expected_default_expression
    assert storage_row.partition_key == test_case.expected_partition_key


@pytest.mark.parametrize(
    "test_case",
    [
        ActualStateProjectionTestCase(
            description="preserves synthesized landing specs and unloaded transform options",
            expected_kafka_columns=(("message", "String", None),),
            expected_kafka_broker_list="kafka:9092",
            expected_kafka_topic="source.orders.created",
            expected_kafka_consumer_group="streambuild_orders_orders",
            expected_kafka_format="JSONAsString",
            expected_kafka_settings={"kafka_num_consumers": "4"},
            expected_raw_columns=(("order_id", "String", None),),
            expected_raw_engine="MergeTree()",
            expected_raw_order_by=("order_id",),
            expected_raw_partition_by="toYYYYMM(created_at)",
            expected_raw_ttl="created_at + INTERVAL 30 DAY",
            expected_raw_settings={"index_granularity": "8192"},
            expected_landing_mv_source="kafka__orders",
            expected_landing_mv_target="raw__orders",
            expected_landing_mv_query="SELECT message AS order_id FROM kafka__orders",
            expected_transform_columns=(("order_id", "String", None),),
            expected_transform_engine="MergeTree()",
            expected_transform_order_by=("order_id",),
            expected_transform_partition_by=None,
            expected_transform_ttl=None,
            expected_transform_settings=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_live_names_and_transform_spec_when_projecting_then_preserves_current_shortcuts(
    test_case: ActualStateProjectionTestCase,
) -> None:
    desired_state: DesiredState
    inspection: ActualStateInspection
    desired_state, inspection = build_projection_characterization_inputs()
    actual_objects: tuple[
        ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView, ...
    ] = build_inspected_actual_objects(desired_state=desired_state, inspection=inspection)
    actual_by_name: dict[
        str, ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView
    ] = {actual_object.name: actual_object for actual_object in actual_objects}
    kafka_table: ActualKafkaTable = cast(ActualKafkaTable, actual_by_name["kafka__orders"])
    raw_table: ActualTable = cast(ActualTable, actual_by_name["raw__orders"])
    landing_mv: ActualMaterializedView = cast(
        ActualMaterializedView,
        actual_by_name["mv__orders_landing"],
    )
    transform_table: ActualTable = cast(ActualTable, actual_by_name["tbl__orders_enriched"])

    assert (
        tuple((column.name, column.type, column.default) for column in kafka_table.columns)
        == test_case.expected_kafka_columns
    )
    assert kafka_table.kafka.broker_list == test_case.expected_kafka_broker_list
    assert kafka_table.kafka.topic == test_case.expected_kafka_topic
    assert kafka_table.kafka.consumer_group == test_case.expected_kafka_consumer_group
    assert kafka_table.kafka.format == test_case.expected_kafka_format
    assert kafka_table.kafka.settings == test_case.expected_kafka_settings
    assert (
        tuple((column.name, column.type, column.default) for column in raw_table.columns)
        == test_case.expected_raw_columns
    )
    assert raw_table.engine == test_case.expected_raw_engine
    assert raw_table.order_by == test_case.expected_raw_order_by
    assert raw_table.partition_by == test_case.expected_raw_partition_by
    assert raw_table.ttl == test_case.expected_raw_ttl
    assert raw_table.settings == test_case.expected_raw_settings
    assert landing_mv.source_table_name == test_case.expected_landing_mv_source
    assert landing_mv.target_table_name == test_case.expected_landing_mv_target
    assert landing_mv.query == test_case.expected_landing_mv_query
    assert (
        tuple((column.name, column.type, column.default) for column in transform_table.columns)
        == test_case.expected_transform_columns
    )
    assert transform_table.engine == test_case.expected_transform_engine
    assert transform_table.order_by == test_case.expected_transform_order_by
    assert transform_table.partition_by == test_case.expected_transform_partition_by
    assert transform_table.ttl == test_case.expected_transform_ttl
    assert transform_table.settings == test_case.expected_transform_settings
