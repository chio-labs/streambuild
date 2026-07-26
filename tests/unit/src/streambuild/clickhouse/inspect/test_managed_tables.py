from collections.abc import Callable, Mapping
from typing import cast

import pytest

from streambuild.clickhouse.inspect._helpers.managed_tables import (
    build_inspected_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from tests.unit.src.streambuild.clickhouse.inspect._test_types import (
    BuildInspectedManagedTableStateTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildInspectedManagedTableStateTestCase(
            description=(
                "ignores materialized view deployment candidates in managed table inspection"
            ),
            system_rows=(
                ("tbl__orders_enriched__dep_a", "MergeTree"),
                ("raw__orders__dep_a", "MergeTree"),
                ("mv__orders_enriched__dep_a", "MaterializedView"),
            ),
            expected_logical_names=("tbl__orders_enriched", "raw__orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_physical_candidates_when_building_inspected_state_then_it_ignores_mv_candidates(
    test_case: BuildInspectedManagedTableStateTestCase,
) -> None:
    class QueryingClient:
        def __init__(self) -> None:
            physical_candidate_rows: tuple[Mapping[str, object], ...] = tuple(
                {"name": name} for name, _engine in test_case.system_rows
            )
            self.response_rows = iter(((), physical_candidate_rows))

        def query_many(
            self,
            *,
            statement: str,
            decode: Callable[[Mapping[str, object]], object],
        ) -> tuple[object, ...]:
            _ = statement
            return tuple(decode(row) for row in next(self.response_rows))

    inspected_state: InspectedManagedTableState = build_inspected_managed_table_state(
        client=cast(ClickHouseClient, QueryingClient()),
        database="analytics",
    )

    assert tuple(candidate.logical_name for candidate in inspected_state.physical_candidates) == (
        test_case.expected_logical_names
    )
