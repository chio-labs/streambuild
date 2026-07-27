"""Immutable compile artifact models."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticArtifactFile:
    """One target-relative deterministic static artifact."""

    relative_path: Path
    contents: str


@dataclass(frozen=True)
class StaticCompileArtifacts:
    """One complete static target generation ready for publication."""

    compiled_files: tuple[StaticArtifactFile, ...]
    manifest_json: str
    dag_json: str
