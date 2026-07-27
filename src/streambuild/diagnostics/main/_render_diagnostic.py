"""Render one structured diagnostic for human-readable CLI output."""

from collections.abc import Mapping
from pathlib import Path

from streambuild.diagnostics._helpers.rendering import render_diagnostic_text
from streambuild.diagnostics.models import CompilerDiagnostic


def render_diagnostic(
    *, diagnostic: CompilerDiagnostic, source_by_path: Mapping[Path, str] | None = None
) -> str:
    """Return stable text for one structured diagnostic."""

    return render_diagnostic_text(
        diagnostic=diagnostic,
        source_by_path={} if source_by_path is None else source_by_path,
    )
