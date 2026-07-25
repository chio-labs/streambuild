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
