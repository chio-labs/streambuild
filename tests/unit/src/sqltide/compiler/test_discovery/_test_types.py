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


@dataclass(frozen=True)
class DiscoverMacroSqlTestTestCase:
    description: str
    file_contents: str
    expected_name: str
    expected_helper_cte_names: tuple[str, ...]
    expected_actual_fragment: str
    expected_expected_fragment: str


@dataclass(frozen=True)
class DiscoverAssertionSqlTestTestCase:
    description: str
    file_contents: str
    expected_assertion_cte_names: tuple[str, ...]
    expected_assertion_reference_names: tuple[str, ...]
    expected_target_names: tuple[str, ...]


@dataclass(frozen=True)
class ScannedSqlTestCteTestCase:
    description: str
    file_contents: str
    expected_cte_names: tuple[str, ...]
    expected_body_fragment: str


@dataclass(frozen=True)
class MacroModeRestrictionTestCase:
    description: str
    macro_file_contents: str
    file_contents: str
    expected_error_fragment: str
