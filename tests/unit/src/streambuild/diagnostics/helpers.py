from pathlib import Path

from streambuild.diagnostics.models import (
    CompilerDiagnostic,
    RelatedDiagnosticLocation,
    SourceLocation,
)
from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


def build_diagnostic() -> CompilerDiagnostic:
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILATION,
        severity=DiagnosticSeverity.ERROR,
        code="STB-COMPILE-TEST",
        message="projection has no alias",
        resource_name="orders",
        location=SourceLocation(
            path=Path("models/orders.sql"),
            line=2,
            column=8,
            end_line=2,
            end_column=12,
        ),
        related_locations=(
            RelatedDiagnosticLocation(
                label="declared here",
                location=SourceLocation(
                    path=Path("models/orders.sql"),
                    line=1,
                    column=1,
                    end_line=1,
                    end_column=5,
                ),
                message="model declaration",
            ),
        ),
        help="alias every projected expression",
    )
