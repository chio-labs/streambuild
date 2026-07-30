from pathlib import Path

import pytest

from streambuild.compiler.pipeline.models import CompileAnalysis
from tests.unit.src.streambuild.compiler.planner.helpers import (
    analyze_direct_scope_project,
    write_direct_scope_project,
)


@pytest.fixture
def direct_scope_analysis(tmp_path: Path) -> CompileAnalysis:
    """Analyze the alpha/beta/gamma/delta scope project used by direct planning tests."""

    write_direct_scope_project(project_root=tmp_path)
    return analyze_direct_scope_project(project_root=tmp_path)
