"""Options and prepared context for the direct build command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DirectPlan


@dataclass(frozen=True)
class BuildCommandOptions:
    """Every operator-supplied option for one `stb build` invocation."""

    pipelines_root: Path
    database: str | None
    metadata_database: str | None
    selectors: tuple[str, ...]
    json_output: bool
    verbose: bool
    auto_approve: bool


@dataclass(frozen=True)
class BuildPreviewContext:
    """The plan and resolved databases a build renders before it writes anything."""

    analysis: CompileAnalysis
    plan: DirectPlan
    database: str
    metadata_database: str
    adapter_name: str
