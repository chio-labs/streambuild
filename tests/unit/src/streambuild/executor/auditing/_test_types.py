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


@dataclass(frozen=True)
class AuditWarmupStateTestCase:
    description: str
    warmup_seconds: int
    anchors_by_model: dict[str, str]
    materialized_model_names: frozenset[str]
    warehouse_now: str
    expected_eligible: bool
    expected_anchor: str | None
    expected_eligible_at: str | None
    expected_missing_model_names: tuple[str, ...]
