from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSqlTestCasesTestCase:
    description: str
    test_file_contents: str
    expected_query_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()
    expected_target_model_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildSqlTestCasesErrorTestCase:
    description: str
    test_file_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SqlTestChainClosureTestCase:
    description: str
    test_file_contents: str
    expected_assembled_cte_names: tuple[str, ...]
    expected_target_model_names: tuple[str, ...]


@dataclass(frozen=True)
class SqlTestAssertionAssemblyTestCase:
    description: str
    test_file_contents: str
    expected_assertion_names: tuple[str, ...]
    expected_assertion_column_names: tuple[str, ...]
    expected_query_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqlTestWarningTestCase:
    description: str
    test_file_contents: str
    expected_warnings: tuple[str, ...]


@dataclass(frozen=True)
class SqlTestDeepChainTestCase:
    description: str
    model_count: int
    expected_terminal_cte_name: str
    expected_assembled_count: int


@dataclass(frozen=True)
class MacroSqlTestAssemblyTestCase:
    description: str
    test_file_contents: str
    expected_target_model_name: str
    expected_column_names: tuple[str, ...]
    expected_query_fragments: tuple[str, ...]
