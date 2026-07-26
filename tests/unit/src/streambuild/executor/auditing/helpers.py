from collections.abc import Iterator

from streambuild.adapter.models import AdapterQueryResult


class FakeAuditClickHouseClient:
    def __init__(
        self,
        *,
        count_result_rows: tuple[tuple[object, ...], ...],
        sample_column_names: tuple[str, ...],
        sample_rows: tuple[tuple[object, ...], ...],
    ) -> None:
        self.count_result_rows = count_result_rows
        self.sample_column_names = sample_column_names
        self.sample_rows = sample_rows
        self.queries: list[str] = []
        self.query_results: Iterator[AdapterQueryResult] = iter(
            (
                AdapterQueryResult(rows=count_result_rows, column_names=("value",)),
                AdapterQueryResult(rows=sample_rows, column_names=sample_column_names),
            )
        )

    def query(self, statement: str) -> AdapterQueryResult:
        self.queries.append(statement)
        return next(self.query_results)
