from collections.abc import Mapping

import pytest

from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import AdapterConnectionConfig, AdapterQueryResult
from tests.unit.src.streambuild.adapter._test_types import (
    AdapterConnectionConfigRedactionTestCase,
    AdapterQueryResultDecodingTestCase,
    AdapterQueryResultErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterQueryResultDecodingTestCase(
            description="decodes every row against its column names",
            column_names=("deployment_id", "status"),
            rows=(("dep_1", "open"), ("dep_2", "failed")),
            expected_named_rows=(
                {"deployment_id": "dep_1", "status": "open"},
                {"deployment_id": "dep_2", "status": "failed"},
            ),
        ),
        AdapterQueryResultDecodingTestCase(
            description="decodes an empty result without column names",
            column_names=(),
            rows=(),
            expected_named_rows=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_normalized_query_result_when_reading_named_rows_then_it_keys_every_row(
    test_case: AdapterQueryResultDecodingTestCase,
) -> None:
    result: AdapterQueryResult = AdapterQueryResult(
        rows=test_case.rows, column_names=test_case.column_names
    )

    named_rows: tuple[Mapping[str, object], ...] = result.named_rows()

    assert named_rows == test_case.expected_named_rows


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterQueryResultErrorTestCase(
            description="rejects rows that arrive without column names",
            column_names=(),
            rows=(("dep_1",),),
            expected_message_fragment="Query result does not include column names",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rows_without_column_names_when_reading_named_rows_then_it_raises(
    test_case: AdapterQueryResultErrorTestCase,
) -> None:
    result: AdapterQueryResult = AdapterQueryResult(
        rows=test_case.rows, column_names=test_case.column_names
    )

    with pytest.raises(AdapterResultError) as error_info:
        result.named_rows()

    assert test_case.expected_message_fragment in str(error_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterConnectionConfigRedactionTestCase(
            description="hides the password when the resolved configuration is rendered",
            password="super-secret-password",
            expected_absent_fragment="super-secret-password",
            expected_present_fragments=("host='localhost'", "password='***'"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_resolved_connection_config_when_rendering_then_it_redacts_the_password(
    test_case: AdapterConnectionConfigRedactionTestCase,
) -> None:
    config: AdapterConnectionConfig = AdapterConnectionConfig(
        host="localhost",
        port=8123,
        username="streambuild",
        password=test_case.password,
    )

    rendered: str = repr(config)

    assert test_case.expected_absent_fragment not in rendered
    expected_fragment: str
    for expected_fragment in test_case.expected_present_fragments:
        assert expected_fragment in rendered
