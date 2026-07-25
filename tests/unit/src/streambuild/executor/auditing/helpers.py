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

    def query(self, statement: str) -> ClickHouseQueryResult:
        self.queries.append(statement)
        if statement.startswith("SELECT count() AS value FROM ("):
            return ClickHouseQueryResult(rows=self.count_result_rows, column_names=("value",))
        return ClickHouseQueryResult(rows=self.sample_rows, column_names=self.sample_column_names)
