"""Diagnostic type declarations."""

from enum import StrEnum


class DiagnosticPhase(StrEnum):
    """Compiler or runtime phase that produced a diagnostic."""

    DISCOVERY = "discovery"
    COMPILATION = "compilation"
    GRAPH = "graph"
    REALIZATION = "realization"
    RUNTIME = "runtime"


class DiagnosticSeverity(StrEnum):
    """Severity of a structured diagnostic."""

    ERROR = "error"
    WARNING = "warning"
