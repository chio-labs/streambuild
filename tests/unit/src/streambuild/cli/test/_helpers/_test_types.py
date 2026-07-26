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
