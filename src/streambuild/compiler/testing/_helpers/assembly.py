"""Assembly helpers for SQL-native test cases."""

from __future__ import annotations

from streambuild.adapter.types import AdapterSetDifferenceComparisonRenderer
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.test_discovery.models import (
    LoadedSqlTest,
    SqlTestMacroPayload,
    SqlTestModelPayload,
)
from streambuild.compiler.test_discovery.types import SqlTestMode
from streambuild.compiler.testing._helpers.comparison import render_comparison_query
from streambuild.compiler.testing._helpers.macro_assembly import build_macro_target
from streambuild.compiler.testing._helpers.model_assembly import (
    build_assertion_steps,
    build_chain_steps,
)
from streambuild.compiler.testing.classes.sql_test_chain_assembler import SqlTestChainAssembler
from streambuild.compiler.testing.exceptions import SqlTestAssemblyError
from streambuild.compiler.testing.models import (
    SqlTestAssertionStep,
    SqlTestCase,
    SqlTestChainStep,
)


def build_sql_test_case(
    *,
    loaded_test: LoadedSqlTest,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    reference_rewriter: SqlReferenceRewriter,
    comparison_renderer: AdapterSetDifferenceComparisonRenderer,
    dialect: str,
) -> SqlTestCase:
    """Assemble one discovered SQL test into an executable comparison statement."""

    if loaded_test.mode == SqlTestMode.MACRO:
        return _build_macro_test_case(
            loaded_test=loaded_test,
            comparison_renderer=comparison_renderer,
            dialect=dialect,
        )
    return _build_model_test_case(
        loaded_test=loaded_test,
        compiled_pipelines=compiled_pipelines,
        reference_rewriter=reference_rewriter,
        comparison_renderer=comparison_renderer,
        dialect=dialect,
    )


def _build_model_test_case(
    *,
    loaded_test: LoadedSqlTest,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    reference_rewriter: SqlReferenceRewriter,
    comparison_renderer: AdapterSetDifferenceComparisonRenderer,
    dialect: str,
) -> SqlTestCase:
    payload: SqlTestModelPayload = _require_model_payload(loaded_test)
    assembler: SqlTestChainAssembler = SqlTestChainAssembler(
        loaded_test=loaded_test,
        payload=payload,
        compiled_pipelines=compiled_pipelines,
        reference_rewriter=reference_rewriter,
    )
    authored_ctes: tuple[tuple[str, str], ...] = tuple(
        (cte.name, cte.query) for cte in loaded_test.authored_ctes
    )
    target_cases: tuple[SqlTestChainStep, ...] = build_chain_steps(
        loaded_test=loaded_test,
        payload=payload,
        assembler=assembler,
        authored_ctes=authored_ctes,
        dialect=dialect,
    )
    assertion_cases: tuple[SqlTestAssertionStep, ...] = build_assertion_steps(
        loaded_test=loaded_test,
        payload=payload,
        assembler=assembler,
        authored_ctes=authored_ctes,
        dialect=dialect,
    )
    return SqlTestCase(
        file_path=loaded_test.file_path,
        query=render_comparison_query(
            comparison_renderer=comparison_renderer,
            target_cases=target_cases,
            assertion_cases=assertion_cases,
        ),
        target_cases=target_cases,
        assertion_cases=assertion_cases,
        warnings=assembler.unreachable_mock_warnings(),
        test_index=loaded_test.test_index,
        name=loaded_test.name,
    )


def _build_macro_test_case(
    *,
    loaded_test: LoadedSqlTest,
    comparison_renderer: AdapterSetDifferenceComparisonRenderer,
    dialect: str,
) -> SqlTestCase:
    payload: SqlTestMacroPayload = _require_macro_payload(loaded_test)
    target_cases: tuple[SqlTestChainStep, ...] = (
        build_macro_target(loaded_test=loaded_test, payload=payload, dialect=dialect),
    )
    return SqlTestCase(
        file_path=loaded_test.file_path,
        query=render_comparison_query(
            comparison_renderer=comparison_renderer,
            target_cases=target_cases,
            assertion_cases=(),
        ),
        target_cases=target_cases,
        test_index=loaded_test.test_index,
        name=loaded_test.name,
    )


def _require_model_payload(loaded_test: LoadedSqlTest) -> SqlTestModelPayload:
    payload: object = loaded_test.payload
    if isinstance(payload, SqlTestModelPayload):
        return payload
    raise SqlTestAssemblyError(f"SQL test '{loaded_test.file_path}' is not a model-mode test")


def _require_macro_payload(loaded_test: LoadedSqlTest) -> SqlTestMacroPayload:
    payload: object = loaded_test.payload
    if isinstance(payload, SqlTestMacroPayload):
        return payload
    raise SqlTestAssemblyError(f"SQL test '{loaded_test.file_path}' is not a macro-mode test")
