from collections.abc import Iterator

from streambuild.integrations.clickhouse.models import ClickHouseQueryResult


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
        self.query_results: Iterator[ClickHouseQueryResult] = iter(
            (
                ClickHouseQueryResult(rows=count_result_rows, column_names=("value",)),
                ClickHouseQueryResult(rows=sample_rows, column_names=sample_column_names),
            )
        )

    def query(self, statement: str) -> ClickHouseQueryResult:
        self.queries.append(statement)
        return next(self.query_results)
