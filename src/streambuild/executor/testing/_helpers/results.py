"""Build per-case SQL test results from one decoded comparison statement."""

from __future__ import annotations

from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.executor.testing._helpers.decoding import decode_comparison_rows
from streambuild.executor.testing.constants import ASSERTION_RESULT_LABEL_PREFIX
from streambuild.executor.testing.models import (
    ComparisonRows,
    SqlTestTargetExecutionResult,
)


def build_target_results(
    *, test_case: SqlTestCase, result: AdapterQueryResult
) -> tuple[SqlTestTargetExecutionResult, ...]:
    """Expand one comparison result into ordered chain and assertion results."""

    labels: tuple[str, ...] = _case_labels(test_case)
    column_names_by_index: tuple[tuple[str, ...], ...] = _case_column_names(test_case)
    rows: ComparisonRows = decode_comparison_rows(
        rows=result.rows,
        case_count=len(labels),
        file_path=test_case.file_path,
    )
    return tuple(
        SqlTestTargetExecutionResult(
            target_model_name=label,
            passed=not rows.missing[index] and not rows.unexpected[index],
            column_names=column_names_by_index[index],
            missing_rows=rows.missing[index],
            unexpected_rows=rows.unexpected[index],
        )
        for index, label in enumerate(labels)
    )


def _case_labels(test_case: SqlTestCase) -> tuple[str, ...]:
    return (
        *(target.target_model_name for target in test_case.target_cases),
        *(
            f"{ASSERTION_RESULT_LABEL_PREFIX}{assertion.name}"
            for assertion in test_case.assertion_cases
        ),
    )


def _case_column_names(test_case: SqlTestCase) -> tuple[tuple[str, ...], ...]:
    return (
        *(target.expected_column_names for target in test_case.target_cases),
        *(assertion.column_names for assertion in test_case.assertion_cases),
    )
