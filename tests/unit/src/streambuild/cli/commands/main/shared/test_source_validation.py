from collections.abc import Callable, Mapping
from typing import cast

import pytest

from streambuild.cli.commands.main.shared.helpers.source_validation import (
    validate_declared_external_sources,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient
from tests.unit.src.streambuild.cli.commands.main.shared._test_types import (
    CliExternalSourceValidationErrorTestCase,
)
from tests.unit.src.streambuild.cli.commands.main.shared.helpers import (
    build_compiled_external_source_pipeline,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliExternalSourceValidationErrorTestCase(
            description="rejects replay alias collision with an existing physical column",
            existing_column_names=(
                "order_id",
                "event_partition",
                "event_offset",
                "event_timestamp",
                "_replay_offset",
            ),
            expected_error_fragment="conflicts with the injected replay alias",
        )
    ],
    ids=["rejects replay alias collision with an existing physical column"],
)
def test_given_external_source_alias_collision_when_validating_then_it_raises_clear_error(
    test_case: CliExternalSourceValidationErrorTestCase,
) -> None:
    client: _FakeClickHouseClient = _FakeClickHouseClient(test_case.existing_column_names)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        validate_declared_external_sources(
            client=cast(ClickHouseClient, client),
            compiled_pipelines=(build_compiled_external_source_pipeline(),),
            database="default",
        )


class _FakeClickHouseClient:
    def __init__(self, existing_column_names: tuple[str, ...]) -> None:
        self._existing_column_names = existing_column_names

    def query_many(
        self,
        query: str,
        *,
        decode: Callable[[Mapping[str, object]], object],
    ) -> tuple[object, ...]:
        del query
        decoded_rows: list[object] = []
        column_name: str
        for column_name in self._existing_column_names:
            column_type: str = "DateTime64(3)" if column_name == "event_timestamp" else "Int64"
            decoded_rows.append(
                decode(cast(Mapping[str, object], {"name": column_name, "type": column_type}))
            )
        return tuple(decoded_rows)
