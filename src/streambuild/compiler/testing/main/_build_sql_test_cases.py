"""Entry point for assembling discovered SQL tests into executable cases."""

from __future__ import annotations

from streambuild.adapter.types import AdapterSetDifferenceComparisonRenderer
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from streambuild.compiler.testing._helpers.assembly import build_sql_test_case
from streambuild.compiler.testing.models import SqlTestCase


def build_sql_test_cases(
    *,
    loaded_tests: tuple[LoadedSqlTest, ...],
    compiled_pipelines: tuple[CompiledPipeline, ...],
    reference_rewriter: SqlReferenceRewriter,
    comparison_renderer: AdapterSetDifferenceComparisonRenderer,
    dialect: str,
) -> tuple[SqlTestCase, ...]:
    """Assemble discovered SQL tests into executable test queries."""

    return tuple(
        build_sql_test_case(
            loaded_test=loaded_test,
            compiled_pipelines=compiled_pipelines,
            reference_rewriter=reference_rewriter,
            comparison_renderer=comparison_renderer,
            dialect=dialect,
        )
        for loaded_test in loaded_tests
    )
