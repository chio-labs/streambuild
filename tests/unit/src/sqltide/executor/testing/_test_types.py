from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonDecodingTestCase:
    description: str
    target_model_names: tuple[str, ...]
    assertion_names: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    expected_labels: tuple[str, ...]
    expected_passed: tuple[bool, ...]
    expected_missing_counts: tuple[int, ...]
    expected_unexpected_counts: tuple[int, ...]


@dataclass(frozen=True)
class ComparisonDecodingErrorTestCase:
    description: str
    rows: tuple[tuple[object, ...], ...]
    set_difference_comparison: bool
    expected_error_fragment: str


@dataclass(frozen=True)
class SqlTestExecutionFailureTestCase:
    description: str
    expected_passed: tuple[bool, ...]
    expected_error_fragment: str
    expected_statements: tuple[str, ...]
