"""SQL test discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.discovery.types import SqlRelationType


@dataclass(frozen=True)
class SqlTestMock:
    """One discovered direct mock boundary in a SQL test file."""

    cte_name: str
    name: str
    relation_type: SqlRelationType | str
    query: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", SqlRelationType(self.relation_type))


@dataclass(frozen=True)
class SqlTestCte:
    """One authored CTE preserved from a SQL-native test file."""

    name: str
    query: str


@dataclass(frozen=True)
class LoadedSqlTest:
    """One discovered SQL test file with extracted mock and expectation CTEs."""

    file_path: Path
    authored_ctes: tuple[SqlTestCte, ...]
    mocks: tuple[SqlTestMock, ...]
    expected_targets: tuple[SqlTestCte, ...]
    name: str | None = None
    test_index: int = 1


@dataclass(frozen=True)
class SqlTestTargetCase:
    """One assembled target comparison inside a SQL-native test case."""

    target_model_name: str
    expected_column_names: tuple[str, ...]
    query: str


@dataclass(frozen=True)
class SqlTestCase:
    """One fully assembled SQL-native test scenario ready for execution."""

    file_path: Path
    target_cases: tuple[SqlTestTargetCase, ...]
    name: str | None = None
    test_index: int = 1
