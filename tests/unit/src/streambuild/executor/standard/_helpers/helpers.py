from collections.abc import Iterator

from streambuild.adapter.models import AdapterQueryResult
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class ScalarBoundaryRecordingConnection(RecordingAdapterConnection):
    def __init__(self, *, query_results: tuple[AdapterQueryResult, ...]) -> None:
        super().__init__()
        self.query_statements: list[str] = []
        self._query_results: Iterator[AdapterQueryResult] = iter(query_results)

    def query(self, statement: str) -> AdapterQueryResult:
        self.query_statements.append(statement)
        return next(self._query_results)
