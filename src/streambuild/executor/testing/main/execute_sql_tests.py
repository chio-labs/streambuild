"""Execute assembled SQL-native tests through the adapter contract."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.models import AdapterQueryResult
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.executor.testing._helpers.results import build_target_results
from streambuild.executor.testing.exceptions import SqlTestExecutionError
from streambuild.executor.testing.models import (
    SqlTestExecutionResult,
    SqlTestTargetExecutionResult,
)


def execute_sql_tests(
    *,
    test_cases: tuple[SqlTestCase, ...],
    client: AdapterConnection,
) -> tuple[SqlTestExecutionResult, ...]:
    """Execute assembled SQL-native tests against the warehouse."""

    _require_comparison_capability(client)
    results: list[SqlTestExecutionResult] = []
    test_case: SqlTestCase
    for test_case in test_cases:
        try:
            result: AdapterQueryResult = client.query(test_case.query)
        except AdapterWarehouseError as error:
            results.append(
                SqlTestExecutionResult(
                    file_path=test_case.file_path,
                    test_index=test_case.test_index,
                    passed=False,
                    target_results=(),
                    executed_sql=test_case.query,
                    warnings=test_case.warnings,
                    name=test_case.name,
                    error_message=str(error),
                )
            )
            continue
        target_results: tuple[SqlTestTargetExecutionResult, ...] = build_target_results(
            test_case=test_case,
            result=result,
        )
        results.append(
            SqlTestExecutionResult(
                file_path=test_case.file_path,
                test_index=test_case.test_index,
                passed=all(target_result.passed for target_result in target_results),
                target_results=target_results,
                executed_sql=test_case.query,
                warnings=test_case.warnings,
                name=test_case.name,
            )
        )
    return tuple(results)


def _require_comparison_capability(client: AdapterConnection) -> None:
    if not client.capabilities.set_difference_comparison:
        raise SqlTestExecutionError(
            "The selected adapter does not support SQL-test set-difference comparison"
        )
