import pytest

from streambuild.adapter.exceptions import AdapterConfigurationError
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    ClickHouseConnectionConfigErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects adapter-owned connection fields not exercised by ClickHouse",
            values=(
                ("host", "localhost"),
                ("port", 8123),
                ("username", "streambuild"),
                ("password", "secret"),
                ("warehouse", "analytics"),
            ),
            expected_error_fragment="unsupported fields: warehouse",
        ),
        ClickHouseConnectionConfigErrorTestCase(
            description="rejects a non-integer ClickHouse port",
            values=(
                ("host", "localhost"),
                ("port", "8123"),
                ("username", "streambuild"),
                ("password", "secret"),
            ),
            expected_error_fragment="requires integer port",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_connection_fields_when_building_config_then_adapter_rejects_them(
    test_case: ClickHouseConnectionConfigErrorTestCase,
) -> None:
    with pytest.raises(AdapterConfigurationError, match=test_case.expected_error_fragment):
        ClickHouseAdapter().build_connection_config(
            values=dict(test_case.values),
            database="analytics",
        )
