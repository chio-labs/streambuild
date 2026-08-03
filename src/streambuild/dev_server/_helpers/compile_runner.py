"""Run one project compile and reduce failures to structured error info."""

from __future__ import annotations

import datetime
import time
from collections.abc import Callable

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server.models import CompileErrorInfo, CompileOutcome
from streambuild.dev_server.types import CompileStateKind
from streambuild.diagnostics.models import CompilerDiagnostic, SourceLocation


def build_compile_outcome(
    *,
    run_compile: Callable[[], CompileAnalysis],
) -> CompileOutcome:
    """Execute one injected compile callable and capture success or failure."""

    compiled_at: str = _utc_now_iso()
    version_key: str = f"{time.monotonic_ns():x}"
    try:
        analysis: CompileAnalysis = run_compile()
    except Exception as error:
        return CompileOutcome(
            state=CompileStateKind.FAILING,
            version_key=version_key,
            compiled_at=compiled_at,
            error=describe_compile_error(error=error),
        )
    return CompileOutcome(
        state=CompileStateKind.OK,
        version_key=version_key,
        compiled_at=compiled_at,
        analysis=analysis,
        timings=analysis.timings,
    )


def describe_compile_error(*, error: Exception) -> CompileErrorInfo:
    """Reduce one compile exception to message plus source coordinates."""

    diagnostic: object = getattr(error, "diagnostic", None)
    if not isinstance(diagnostic, CompilerDiagnostic):
        return CompileErrorInfo(message=str(error))
    location: SourceLocation | None = diagnostic.location
    if location is None:
        return CompileErrorInfo(message=diagnostic.message)
    return CompileErrorInfo(
        message=diagnostic.message,
        path=str(location.path),
        line=location.line,
        column=location.column,
        end_line=location.end_line,
        end_column=location.end_column,
    )


def _utc_now_iso() -> str:
    return datetime.datetime.now(tz=datetime.UTC).isoformat(timespec="seconds")
