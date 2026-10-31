"""Serialize one structured diagnostic for machine-readable output."""

from sqltide.diagnostics._helpers.rendering import render_diagnostic_json_text
from sqltide.diagnostics.models import CompilerDiagnostic


def render_diagnostic_json(*, diagnostic: CompilerDiagnostic) -> str:
    """Return deterministic JSON for one structured diagnostic."""

    return render_diagnostic_json_text(diagnostic=diagnostic)
