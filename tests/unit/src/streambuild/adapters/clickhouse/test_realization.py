from typing import cast

import pytest

from streambuild.adapter.exceptions import AdapterConfigurationError
from streambuild.adapter.models import (
    AdapterAdoptedSourceRealizationRequest,
    AdapterColumn,
    AdapterManagedSource,
    AdapterManagedSourceRealizationRequest,
    AdapterMaterializedView,
    AdapterModelRealization,
    AdapterModelRealizationRequest,
    AdapterSourceRealization,
    AdapterTable,
    AdapterView,
    AdapterViewRealizationRequest,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    ClickHouseManagedSourceRealizationTestCase,
    ClickHouseModelRealizationTestCase,
    ClickHouseSourceRealizationErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseManagedSourceRealizationTestCase(
            description="realizes one managed source as three ordered ClickHouse resources",
            expected_relation_name="raw__orders",
            expected_resource_names=("kafka__orders", "raw__orders", "mv__orders"),
            expected_consumer_group="streambuild_orders_orders",
            expected_landing_ttl="_replay_landed_at + INTERVAL 7 DAY",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_managed_source_request_when_realizing_then_returns_expected_resources(
    test_case: ClickHouseManagedSourceRealizationTestCase,
) -> None:
    realization: AdapterSourceRealization = ClickHouseAdapter().realize_source(
        request=AdapterManagedSourceRealizationRequest(
            logical_name="orders",
            source_kind="kafka",
            broker_list="kafka:9092",
            topic="source.orders",
            consumer_group=None,
            format="JSONAsString",
            ttl="_replay_landed_at + INTERVAL 7 DAY",
        )
    )
    managed_source: AdapterManagedSource = cast(AdapterManagedSource, realization.resources[0])
    landing_table: AdapterTable = cast(AdapterTable, realization.resources[1])

    assert realization.relation_name == test_case.expected_relation_name
    assert tuple(resource.name for resource in realization.resources) == (
        test_case.expected_resource_names
    )
    assert managed_source.consumer_group == test_case.expected_consumer_group
    assert landing_table.ttl == test_case.expected_landing_ttl


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseManagedSourceRealizationTestCase(
            description="adopts an existing source without claiming adapter resources",
            expected_relation_name="existing_orders",
            expected_resource_names=(),
            expected_consumer_group="",
            expected_landing_ttl=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adopted_source_request_when_realizing_then_claims_no_resources(
    test_case: ClickHouseManagedSourceRealizationTestCase,
) -> None:
    realization: AdapterSourceRealization = ClickHouseAdapter().realize_source(
        request=AdapterAdoptedSourceRealizationRequest(
            logical_name="orders",
            relation_name="existing_orders",
        )
    )

    assert realization.relation_name == test_case.expected_relation_name
    assert tuple(resource.name for resource in realization.resources) == (
        test_case.expected_resource_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseSourceRealizationErrorTestCase(
            description="rejects unsupported managed source format",
            source_format="JSONEachRow",
            settings=(),
            expected_error_type=AdapterConfigurationError,
            expected_error_fragment="supports only the 'JSONAsString' format",
        ),
        ClickHouseSourceRealizationErrorTestCase(
            description="rejects managed source settings that replace typed fields",
            source_format="JSONAsString",
            settings=(("kafka_group_name", "override"),),
            expected_error_type=AdapterConfigurationError,
            expected_error_fragment="cannot redefine typed Kafka settings",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_managed_source_request_when_realizing_then_raises_clear_error(
    test_case: ClickHouseSourceRealizationErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        ClickHouseAdapter().realize_source(
            request=AdapterManagedSourceRealizationRequest(
                logical_name="orders",
                source_kind="kafka",
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group=None,
                format=test_case.source_format,
                settings=test_case.settings,
            )
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseModelRealizationTestCase(
            description="realizes one logical model as one table and one materialized view",
            expected_relation_name="tbl__orders_enriched",
            expected_resource_names=("tbl__orders_enriched", "mv__orders_enriched"),
            expected_source_relation_name="raw__orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_model_request_when_realizing_then_returns_two_resources(
    test_case: ClickHouseModelRealizationTestCase,
) -> None:
    realization: AdapterModelRealization = ClickHouseAdapter().realize_model(
        request=AdapterModelRealizationRequest(
            logical_name="orders_enriched",
            target_relation_name="tbl__orders_enriched",
            source_relation_name="raw__orders",
            resolved_query="SELECT order_id FROM raw__orders",
            resolved_database_template=(
                "SELECT order_id FROM __streambuild_target_database__.raw__orders"
            ),
            columns=(AdapterColumn(name="order_id", type="UInt64"),),
            engine="MergeTree()",
            order_by=("order_id",),
        )
    )
    table: AdapterTable = cast(AdapterTable, realization.resources[0])
    view: AdapterMaterializedView = cast(AdapterMaterializedView, realization.resources[1])

    assert realization.relation_name == test_case.expected_relation_name
    assert (table.name, view.name) == test_case.expected_resource_names
    assert view.source_relation_name == test_case.expected_source_relation_name


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseModelRealizationTestCase(
            description="realizes an exact ordinary view name as one query-only resource",
            expected_relation_name="customer_orders",
            expected_resource_names=("customer_orders",),
            expected_source_relation_name="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_view_request_when_realizing_then_returns_one_view_resource(
    test_case: ClickHouseModelRealizationTestCase,
) -> None:
    realization: AdapterModelRealization = ClickHouseAdapter().realize_model(
        request=AdapterViewRealizationRequest(
            logical_name="orders_view",
            target_relation_name="customer_orders",
            resolved_query="SELECT order_id FROM orders",
            resolved_database_template=(
                "SELECT order_id FROM __streambuild_target_database__.orders"
            ),
        )
    )

    view: AdapterView = cast(AdapterView, realization.resources[0])
    assert isinstance(view, AdapterView)
    assert realization.relation_name == test_case.expected_relation_name
    assert (view.name,) == test_case.expected_resource_names
    assert realization.resources == (view,)
