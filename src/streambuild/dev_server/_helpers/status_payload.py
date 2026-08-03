"""Serialize compile and warehouse state into the /api/status payload."""

from __future__ import annotations

from dataclasses import asdict

from streambuild.compiler.pipeline.models import CompilationTimings
from streambuild.dev_server.models import CompileErrorInfo, CompileOutcome


def build_status_payload(
    *,
    outcome: CompileOutcome,
    warehouse_connected: bool,
    warehouse_database: str | None,
    warehouse_error: str | None,
) -> dict[str, object]:
    """Build the cheap polled status payload."""

    return {
        "compile": {
            "state": str(outcome.state),
            "versionKey": outcome.version_key,
            "compiledAt": outcome.compiled_at,
            "timings": _timings_payload(outcome.timings),
            "error": _error_payload(outcome.error),
        },
        "warehouse": {
            "connected": warehouse_connected,
            "database": warehouse_database,
            "error": warehouse_error,
        },
    }


def _timings_payload(timings: CompilationTimings | None) -> dict[str, int] | None:
    if timings is None:
        return None
    return {
        "discoveryMs": timings.discovery_ms,
        "compileInputsMs": timings.compile_inputs_ms,
        "assemblyMs": timings.assembly_ms,
        "graphMs": timings.graph_ms,
        "realizationMs": timings.realization_ms,
    }


def _error_payload(error: CompileErrorInfo | None) -> dict[str, object] | None:
    if error is None:
        return None
    return asdict(error)
