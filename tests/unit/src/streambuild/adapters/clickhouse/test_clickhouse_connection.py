from typing import cast

import pytest
from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.adapter.exceptions import (
    AdapterAuthenticationError,
    AdapterRelationNotFoundError,
    AdapterWarehouseError,
)
from streambuild.adapter.models import AdapterQueryResult
from streambuild.adapters.clickhouse.classes.clickhouse_connection import ClickHouseConnection
from streambuild.adapters.clickhouse.types import RawClickHouseClient
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    ConnectionQueryNormalizationTestCase,
    ConnectionTranslationTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
    FailingRawClickHouseClient,
    FakeRawClickHouseQueryResult,
    StubRawClickHouseClient,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionQueryNormalizationTestCase(
            description="normalizes driver sequences into immutable neutral results",
            raw_column_names=["deployment_id", "status"],
            raw_result_rows=[["dep_1", "open"], ["dep_2", "failed"]],
            expected_column_names=("deployment_id", "status"),
            expected_rows=(("dep_1", "open"), ("dep_2", "failed")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_driver_rows_when_querying_through_the_adapter_then_it_returns_neutral_tuples(
    test_case: ConnectionQueryNormalizationTestCase,
) -> None:
    raw_client: StubRawClickHouseClient = StubRawClickHouseClient(
        FakeRawClickHouseQueryResult(
            column_names=test_case.raw_column_names,
            result_rows=test_case.raw_result_rows,
        )
    )
    connection: ClickHouseConnection = ClickHouseConnection(cast(RawClickHouseClient, raw_client))

    result: AdapterQueryResult = connection.query("SELECT deployment_id, status FROM deployments")

    assert result.column_names == test_case.expected_column_names
    assert result.rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a query relation failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Table analytics.tbl__orders does not exist. "
                "(UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        ),
        ConnectionTranslationTestCase(
            description="translates a query authentication failure",
            driver_error=OperationalError(
                "Code: 516. DB::Exception: Authentication failed. (AUTHENTICATION_FAILED)"
            ),
            expected_error_type=AdapterAuthenticationError,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_querying_then_no_driver_exception_escapes(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.query("SELECT 1")

    assert type(error_info.value) is test_case.expected_error_type
    assert not isinstance(error_info.value, DatabaseError | OperationalError)


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a command relation failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Table analytics.tbl__orders does not exist. "
                "(UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_commanding_then_it_raises_the_neutral_equivalent(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.command("DROP TABLE analytics.tbl__orders")

    assert type(error_info.value) is test_case.expected_error_type


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates an insert relation failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Table analytics.tbl__orders does not exist. "
                "(UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_inserting_rows_then_it_raises_the_neutral_equivalent(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.insert_rows(table="analytics.tbl__orders", rows=({"order_id": "order-1"},))

    assert type(error_info.value) is test_case.expected_error_type


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionTranslationTestCase(
            description="translates a close failure",
            driver_error=DatabaseError(
                "Code: 60. DB::Exception: Connection target disappeared. (UNKNOWN_TABLE)"
            ),
            expected_error_type=AdapterRelationNotFoundError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_when_closing_then_it_raises_the_neutral_equivalent(
    test_case: ConnectionTranslationTestCase,
) -> None:
    connection: ClickHouseConnection = ClickHouseConnection(
        cast(RawClickHouseClient, FailingRawClickHouseClient(test_case.driver_error))
    )

    with pytest.raises(AdapterWarehouseError) as error_info:
        connection.close()

    assert type(error_info.value) is test_case.expected_error_type
