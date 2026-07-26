"""Pipeline discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.spec.models import Pipeline, Project


@dataclass(frozen=True)
class LoadedPipeline:
    """A discovered pipeline plus the file it was loaded from."""

    pipeline: Pipeline
    file_path: Path
    project: Project | None = None
