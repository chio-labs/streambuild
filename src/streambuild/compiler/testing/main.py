"""Entry point for compiler-side SQL test assembly."""

from __future__ import annotations

from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.shared.models import LoadedSqlTest
from streambuild.compiler.testing.helpers.assembly import build_sql_test_case
from streambuild.compiler.testing.models import SqlTestCase


def build_sql_test_cases(
    *,
    loaded_tests: tuple[LoadedSqlTest, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
) -> tuple[SqlTestCase, ...]:
    """Assemble discovered SQL tests into executable test queries."""

    return tuple(
        build_sql_test_case(loaded_test=loaded_test, compiled_pipelines=compiled_pipelines)
        for loaded_test in loaded_tests
    )
