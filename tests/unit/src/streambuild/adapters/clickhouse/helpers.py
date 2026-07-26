from collections.abc import Iterator, Sequence


class FakeRawClickHouseQueryResult:
    """A raw driver result shape used to exercise adapter normalization."""

    def __init__(self, *, column_names: list[str], result_rows: list[list[object]]) -> None:
        self.column_names: Sequence[str] = column_names
        self.result_rows: Sequence[Sequence[object]] = result_rows


class StubRawClickHouseClient:
    """A raw driver client returning one prepared result for every query."""

    def __init__(self, result: FakeRawClickHouseQueryResult) -> None:
        self._result: FakeRawClickHouseQueryResult = result
        self.closed: bool = False

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        del statement
        return self._result

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names

    def close(self) -> None:
        self.closed = True


class SequencedRawClickHouseClient:
    """A raw client returning a prepared result sequence while recording queries."""

    def __init__(self, results: tuple[FakeRawClickHouseQueryResult, ...]) -> None:
        self._results: Iterator[FakeRawClickHouseQueryResult] = iter(results)
        self.statements: list[str] = []

    def command(self, statement: str) -> None:
        del statement

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        self.statements.append(statement)
        return next(self._results)

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names

    def close(self) -> None:
        return None


class FailingRawClickHouseClient:
    """A raw driver client that always raises one prepared driver error."""

    def __init__(self, error: Exception) -> None:
        self._error: Exception = error

    def command(self, statement: str) -> None:
        del statement
        raise self._error

    def query(self, statement: str) -> FakeRawClickHouseQueryResult:
        del statement
        raise self._error

    def insert(self, *, table: str, data: list[list[object]], column_names: list[str]) -> None:
        del table, data, column_names
        raise self._error

    def close(self) -> None:
        raise self._error
