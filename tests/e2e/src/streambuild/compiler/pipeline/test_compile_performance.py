from pathlib import Path

import pytest

from tests.e2e.src.streambuild.compiler.pipeline._test_types import (
    CompilePerformanceTestCase,
)
from tests.e2e.src.streambuild.compiler.pipeline.helpers import run_compile_benchmark


@pytest.mark.e2e
@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        CompilePerformanceTestCase(
            description="3000 model project compiles under the accepted measured budget",
            model_count=3000,
            expected_max_seconds=25.0,
        ),
        CompilePerformanceTestCase(
            description="10000 model project compiles under the accepted measured budget",
            model_count=10000,
            expected_max_seconds=75.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_project_when_compiling_then_finishes_within_budget(
    test_case: CompilePerformanceTestCase,
    tmp_path: Path,
) -> None:
    elapsed_seconds: float = run_compile_benchmark(
        project_dir=tmp_path / f"project_{test_case.model_count}",
        model_count=test_case.model_count,
    )
    assert elapsed_seconds < test_case.expected_max_seconds
