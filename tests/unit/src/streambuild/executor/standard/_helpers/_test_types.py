from dataclasses import dataclass


@dataclass(frozen=True)
class ScalarBoundaryTestCase:
    description: str
    source_maximum: str
    expected_query_statements: tuple[str, ...]
    expected_cutoff_value: str
