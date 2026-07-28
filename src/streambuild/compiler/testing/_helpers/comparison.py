"""Build one neutral bag-comparison request for an assembled SQL test."""

from __future__ import annotations

from streambuild.adapter.models import (
    AdapterSetDifferenceComparisonRequest,
    AdapterSetDifferenceTarget,
)
from streambuild.adapter.types import AdapterSetDifferenceComparisonRenderer
from streambuild.compiler.testing.constants import ASSERTION_TARGET_LABEL_PREFIX
from streambuild.compiler.testing.models import SqlTestAssertionStep, SqlTestChainStep


def render_comparison_query(
    *,
    comparison_renderer: AdapterSetDifferenceComparisonRenderer,
    target_cases: tuple[SqlTestChainStep, ...],
    assertion_cases: tuple[SqlTestAssertionStep, ...],
) -> str:
    """Render every chain and assertion comparison as one adapter statement."""

    return comparison_renderer(
        request=AdapterSetDifferenceComparisonRequest(
            targets=(
                *(_chain_target(step=step) for step in target_cases),
                *(_assertion_target(step=step) for step in assertion_cases),
            )
        )
    )


def _chain_target(*, step: SqlTestChainStep) -> AdapterSetDifferenceTarget:
    return AdapterSetDifferenceTarget(
        name=step.target_model_name,
        column_names=step.expected_column_names,
        ctes=step.ctes,
        actual_query=step.actual_query,
        expected_query=step.expected_query,
    )


def _assertion_target(*, step: SqlTestAssertionStep) -> AdapterSetDifferenceTarget:
    return AdapterSetDifferenceTarget(
        name=f"{ASSERTION_TARGET_LABEL_PREFIX}{step.name}",
        column_names=step.column_names,
        ctes=step.ctes,
        actual_query=step.query,
        expected_query=None,
    )
