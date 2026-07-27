"""Serialize one structured diagnostic for machine-readable output."""

from streambuild.diagnostics._helpers.rendering import render_diagnostic_json_text
from streambuild.diagnostics.models import CompilerDiagnostic


def render_diagnostic_json(*, diagnostic: CompilerDiagnostic) -> str:
    """Return deterministic JSON for one structured diagnostic."""

    return render_diagnostic_json_text(diagnostic=diagnostic)
