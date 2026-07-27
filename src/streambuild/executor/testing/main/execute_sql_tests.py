"""Entry point for executing SQL-native tests against ClickHouse."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.test_discovery.models import SqlTestCase, SqlTestTargetCase
from streambuild.executor.testing.constants import (
    MISSING_DIFF_TYPE,
    UNEXPECTED_DIFF_TYPE,
)
from streambuild.executor.testing.exceptions import SqlTestExecutionError
from streambuild.executor.testing.models import SqlTestExecutionResult, SqlTestTargetExecutionResult


def execute_sql_tests(
    *,
    test_cases: tuple[SqlTestCase, ...],
    client: AdapterConnection,
) -> tuple[SqlTestExecutionResult, ...]:
    """Execute assembled SQL-native tests against ClickHouse."""

    results: list[SqlTestExecutionResult] = []
    test_case: SqlTestCase
    for test_case in test_cases:
        target_results: list[SqlTestTargetExecutionResult] = []
        target_case: SqlTestTargetCase
        for target_case in test_case.target_cases:
            result: AdapterQueryResult = client.query(target_case.query)
            missing_rows: list[tuple[object, ...]] = []
            unexpected_rows: list[tuple[object, ...]] = []
            raw_row: tuple[object, ...]
            for raw_row in result.rows:
                diff_type: object = raw_row[0]
                data_row: tuple[object, ...] = raw_row[1:]
                if diff_type == MISSING_DIFF_TYPE:
                    missing_rows.append(data_row)
                    continue
                if diff_type == UNEXPECTED_DIFF_TYPE:
                    unexpected_rows.append(data_row)
                    continue
                raise SqlTestExecutionError(
                    f"SQL test query for '{test_case.file_path}' returned unsupported diff type "
                    f"'{diff_type}'"
                )
            target_results.append(
                SqlTestTargetExecutionResult(
                    target_model_name=target_case.target_model_name,
                    passed=not result.rows,
                    column_names=target_case.expected_column_names,
                    missing_rows=tuple(missing_rows),
                    unexpected_rows=tuple(unexpected_rows),
                )
            )
        results.append(
            SqlTestExecutionResult(
                file_path=test_case.file_path,
                test_index=test_case.test_index,
                passed=all(target_result.passed for target_result in target_results),
                target_results=tuple(target_results),
                name=test_case.name,
            )
        )
    return tuple(results)
