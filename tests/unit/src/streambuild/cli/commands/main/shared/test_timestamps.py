from __future__ import annotations

from typing import cast

import pytest

from streambuild.cli.commands.main.shared._helpers.timestamps import (
    convert_utc_timestamp_for_clickhouse,
    normalize_cli_start_time,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseQueryResult
from tests.unit.src.streambuild.cli.commands.main.shared._test_types import (
    CliStartTimeConversionTestCase,
    CliStartTimeNormalizationErrorTestCase,
    CliStartTimeNormalizationTestCase,
)

NORMALIZATION_TEST_CASES: list[CliStartTimeNormalizationTestCase] = [
    CliStartTimeNormalizationTestCase(
        description="normalizes plain date to midnight utc",
        raw_value="2026-04-01",
        expected_normalized_value="2026-04-01 00:00:00.000",
    ),
    CliStartTimeNormalizationTestCase(
        description="normalizes utc datetime without z suffix",
        raw_value="2026-04-01T12:30:45",
        expected_normalized_value="2026-04-01 12:30:45.000",
    ),
    CliStartTimeNormalizationTestCase(
        description="normalizes fractional utc datetime with z suffix",
        raw_value="2026-04-01T12:30:45.123Z",
        expected_normalized_value="2026-04-01 12:30:45.123",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    NORMALIZATION_TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_valid_cli_start_time_when_normalizing_then_it_returns_internal_timestamp(
    test_case: CliStartTimeNormalizationTestCase,
) -> None:
    normalized_value: str = normalize_cli_start_time(test_case.raw_value)

    assert normalized_value == test_case.expected_normalized_value


@pytest.mark.parametrize(
    "test_case",
    [
        CliStartTimeNormalizationErrorTestCase(
            description="rejects non utc offset timestamps",
            raw_value="2026-04-01T12:30:45+02:00",
            expected_error_fragment="--start-time must be YYYY-MM-DD",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_cli_start_time_when_normalizing_then_it_raises_clear_error(
    test_case: CliStartTimeNormalizationErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        normalize_cli_start_time(test_case.raw_value)


@pytest.mark.parametrize(
    "test_case",
    [
        CliStartTimeConversionTestCase(
            description="converts utc timestamp into clickhouse server timezone",
            timezone_name="Europe/London",
            utc_timestamp="2026-04-01 12:30:45.000",
            expected_converted_value="2026-04-01 13:30:45.000",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_timezone_when_converting_then_it_returns_server_basis_timestamp(
    test_case: CliStartTimeConversionTestCase,
) -> None:
    client: ClickHouseClient = cast(
        ClickHouseClient,
        FakeTimestampCliClickHouseClient(test_case.timezone_name),
    )

    converted_value: str = convert_utc_timestamp_for_clickhouse(
        client=client, utc_timestamp=test_case.utc_timestamp
    )

    assert converted_value == test_case.expected_converted_value


class FakeTimestampCliClickHouseClient:
    def __init__(self, timezone_name: str) -> None:
        self._timezone_name: str = timezone_name

    def query(self, statement: str) -> ClickHouseQueryResult:
        assert statement == "SELECT timezone()"
        return ClickHouseQueryResult(rows=((self._timezone_name,),), column_names=("timezone()",))
