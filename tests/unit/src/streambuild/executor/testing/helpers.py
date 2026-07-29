from pathlib import Path

from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.testing.models import (
    SqlTestAssertionStep,
    SqlTestCase,
    SqlTestChainStep,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class StubComparisonConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        rows: tuple[tuple[object, ...], ...] = (),
        set_difference_comparison: bool = True,
    ) -> None:
        super().__init__(set_difference_comparison=set_difference_comparison)
        self._rows: tuple[tuple[object, ...], ...] = rows

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return AdapterQueryResult(rows=self._rows)


class FailingFirstComparisonConnection(RecordingAdapterConnection):
    def __init__(self) -> None:
        super().__init__(set_difference_comparison=True)
        self._queries = iter((self._raise_warehouse_error, self._empty_result))

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return next(self._queries)()

    def _raise_warehouse_error(self) -> AdapterQueryResult:
        raise AdapterWarehouseError("warehouse rejected test SQL")

    def _empty_result(self) -> AdapterQueryResult:
        return AdapterQueryResult(rows=())


def build_chain_test_case(
    *,
    target_model_names: tuple[str, ...] = ("order_items",),
    assertion_names: tuple[str, ...] = (),
    query: str = "SELECT 1",
    warnings: tuple[str, ...] = (),
) -> SqlTestCase:
    return SqlTestCase(
        file_path=Path("/project/tests/order_events/test_line_total.sql"),
        query=query,
        target_cases=tuple(
            SqlTestChainStep(
                target_model_name=target_model_name,
                expected_column_names=("order_id", "line_total"),
                ctes=(),
                actual_query="SELECT order_id, line_total FROM __model__order_items",
                expected_query="SELECT 'ord_001' AS order_id, 20.0 AS line_total",
            )
            for target_model_name in target_model_names
        ),
        assertion_cases=tuple(
            SqlTestAssertionStep(
                name=assertion_name,
                column_names=("order_id",),
                ctes=(),
                query="SELECT order_id FROM __model__order_items WHERE line_total IS NULL",
            )
            for assertion_name in assertion_names
        ),
        warnings=warnings,
        name="line total computes correctly",
    )
