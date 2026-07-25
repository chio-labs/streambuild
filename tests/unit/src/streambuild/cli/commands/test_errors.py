from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

import pytest
from clickhouse_connect.driver.exceptions import DatabaseError

from streambuild.cli.commands.main.publish.main import run_publish
from streambuild.cli.commands.main.shared._helpers.errors import render_expected_clickhouse_error
from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.unit.src.streambuild.cli.commands._test_types import (
    CliCommandErrorTestCase,
    CliExpectedErrorRenderingTestCase,
)

ERROR_RENDERING_TEST_CASES: list[CliExpectedErrorRenderingTestCase] = [
    CliExpectedErrorRenderingTestCase(
        description="renders authentication failure message",
        error_message=("Code: 516. DB::Exception: Authentication failed. (AUTHENTICATION_FAILED)"),
        expected_fragments=(
            "Publish could not start",
            "Database: flights_demo",
            "ClickHouse rejected the supplied credentials",
            "username and password",
        ),
    ),
    CliExpectedErrorRenderingTestCase(
        description="renders missing database message",
        error_message=(
            "Code: 81. DB::Exception: Database flights_demo does not exist. (UNKNOWN_DATABASE)"
        ),
        expected_fragments=(
            "Publish could not start",
            "Database: flights_demo",
            "target ClickHouse database does not exist",
            "run stb backfill first",
        ),
    ),
    CliExpectedErrorRenderingTestCase(
        description="renders missing metadata table message",
        error_message=(
            "Code: 60. DB::Exception: Unknown table expression identifier "
            "streambuild_deployments. (UNKNOWN_TABLE)"
        ),
        expected_fragments=(
            "Publish could not start",
            "Database: flights_demo",
            "StreamBuild metadata tables do not exist",
            "run stb backfill first",
        ),
    ),
    CliExpectedErrorRenderingTestCase(
        description="renders generic missing table message",
        error_message=(
            "Code: 60. DB::Exception: Table flights_demo.tbl__orders does not exist. "
            "(UNKNOWN_TABLE)"
        ),
        expected_fragments=(
            "Publish could not start",
            "Database: flights_demo",
            "Table flights_demo.tbl__orders does not exist",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_RENDERING_TEST_CASES,
    ids=[case.description for case in ERROR_RENDERING_TEST_CASES],
)
def test_given_expected_clickhouse_error_when_rendering_then_it_returns_operator_message(
    test_case: CliExpectedErrorRenderingTestCase,
) -> None:
    rendered: str | None = render_expected_clickhouse_error(
        command_name="publish",
        database="flights_demo",
        error=DatabaseError(test_case.error_message),
    )

    assert rendered is not None
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        CliCommandErrorTestCase(
            description="publish handles missing database cleanly",
            error_message=(
                "Code: 81. DB::Exception: Database flights_demo does not exist. (UNKNOWN_DATABASE)"
            ),
            expected_exit_code=1,
            expected_error_fragments=(
                "Publish could not start",
                "Database: flights_demo",
                "run stb backfill first",
            ),
        )
    ],
    ids=["publish handles missing database cleanly"],
)
def test_given_missing_database_when_running_publish_then_it_prints_friendly_error(
    test_case: CliCommandErrorTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingClient:
        def query(self, _statement: str) -> object:
            raise DatabaseError(test_case.error_message)

        def query_many(
            self,
            statement: str,
            *,
            decode: Callable[[Mapping[str, object]], object],
        ) -> tuple[object, ...]:
            self.query(statement)
            return ()

        def query_one(
            self,
            statement: str,
            *,
            decode: Callable[[Mapping[str, object]], object],
        ) -> object | None:
            self.query(statement)
            return None

        def close(self) -> None:
            return None

    exit_code: int = run_publish(
        database="flights_demo",
        metadata_database=None,
        deployment_id=None,
        json_output=False,
        client=cast(ClickHouseClient, FailingClient()),
    )
    captured_error: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    expected_fragment: str
    for expected_fragment in test_case.expected_error_fragments:
        assert expected_fragment in captured_error
