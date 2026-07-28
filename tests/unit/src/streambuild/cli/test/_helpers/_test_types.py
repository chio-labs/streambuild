from dataclasses import dataclass


@dataclass(frozen=True)
class SelectLoadedSqlTestsTestCase:
    description: str
    selectors: tuple[str, ...]
    paths: tuple[str, ...]
    expected_target_model_names: tuple[str, ...]


@dataclass(frozen=True)
class SelectLoadedSqlTestsErrorTestCase:
    description: str
    selectors: tuple[str, ...]
    paths: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class RenderSqlTestResultsTestCase:
    description: str
    verbose: bool
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeTestArtifactTestCase:
    description: str
    target_model_names: tuple[str, ...]
    test_name: str
    executed_sql: str
    expected_relative_path: str


@dataclass(frozen=True)
class MacroSqlTestSelectionTestCase:
    description: str
    selectors: tuple[str, ...]
    paths: tuple[str, ...]
    expected_selected_file_names: tuple[str, ...]
