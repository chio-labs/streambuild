"""SQL test discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.discovery.types import SqlRelationType
from streambuild.compiler.test_discovery.types import SqlTestMode


@dataclass(frozen=True)
class SqlTestHeader:
    """One parsed TEST(...) header."""

    name: str | None
    mode: SqlTestMode


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
class SqlTestModelPayload:
    """Mocks, expectations, and assertions authored by one model-mode test."""

    mocks: tuple[SqlTestMock, ...]
    expected_targets: tuple[SqlTestCte, ...]
    assertions: tuple[SqlTestCte, ...]
    assertion_reference_names: tuple[str, ...]


@dataclass(frozen=True)
class SqlTestMacroPayload:
    """The actual and expected comparison authored by one macro-mode test."""

    actual: SqlTestCte
    expected: SqlTestCte


@dataclass(frozen=True)
class LoadedSqlTest:
    """One discovered SQL test block with its classified authored CTEs."""

    file_path: Path
    mode: SqlTestMode
    authored_ctes: tuple[SqlTestCte, ...]
    payload: SqlTestModelPayload | SqlTestMacroPayload
    name: str | None = None
    test_index: int = 1
