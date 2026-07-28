from pathlib import Path

import pytest

from streambuild.compiler.pipeline.models import CompileAnalysis
from tests.unit.src.streambuild.compiler.planner.helpers import (
    analyze_standard_scope_project,
    write_standard_scope_project,
)


@pytest.fixture
def standard_scope_analysis(tmp_path: Path) -> CompileAnalysis:
    """Analyze the alpha/beta/gamma/delta scope project used by standard planning tests."""

    write_standard_scope_project(project_root=tmp_path)
    return analyze_standard_scope_project(project_root=tmp_path)
