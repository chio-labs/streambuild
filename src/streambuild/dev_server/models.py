"""Dev server result models."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from streambuild.compiler.pipeline.models import CompilationTimings, CompileAnalysis
from streambuild.dev_server.types import CompileStateKind


@dataclass(frozen=True)
class CompileErrorInfo:
    """A compile failure reduced to what an error page needs."""

    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None


@dataclass(frozen=True)
class CompileOutcome:
    """One held project compile: either servable definitions or the failure."""

    state: CompileStateKind
    version_key: str
    compiled_at: str
    analysis: CompileAnalysis | None = None
    timings: CompilationTimings | None = None
    error: CompileErrorInfo | None = None


class ChecksRunRequest(BaseModel):
    """POST /api/checks/run body."""

    kind: str
    name: str


class BuildRunRequest(BaseModel):
    """POST /api/build body."""

    selectors: list[str] = []
    startTime: str | None = None  # noqa: N815 - wire format is camelCase
