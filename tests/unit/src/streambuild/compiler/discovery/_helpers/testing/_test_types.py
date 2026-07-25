from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverSqlTestsTestCase:
    description: str
    relative_file_path: str
    file_contents: str
    expected_target_model_names: tuple[str, ...]
    expected_authored_cte_names: tuple[str, ...]
    expected_mock_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverSqlTestsWithMacrosTestCase:
    description: str
    macro_file_contents: str
    test_file_contents: str
    expected_mock_query_fragment: str


@dataclass(frozen=True)
class DiscoverMultipleSqlTestsInFileTestCase:
    description: str
    file_contents: str
    expected_target_model_names: tuple[str, ...]
    expected_test_indexes: tuple[int, ...]
    expected_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverSqlTestsErrorTestCase:
    description: str
    relative_file_path: str
    file_contents: str
    expected_error_fragment: str
