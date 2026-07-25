from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteSqlAuditsTestCase:
    description: str
    audit_query: str
    resolver: dict[str, str]
    count_result_rows: tuple[tuple[object, ...], ...]
    sample_column_names: tuple[str, ...]
    sample_rows: tuple[tuple[object, ...], ...]
    expected_passed: bool
    expected_failing_row_count: int
