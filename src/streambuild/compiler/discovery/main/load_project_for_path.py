"""Load the StreamBuild project that owns a filesystem path."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery._helpers.load import (
    find_project_file,
    load_project_yaml,
)
from streambuild.spec.models.project import Project


def load_project_for_path(path: Path) -> Project | None:
    """Load the nearest project config for a path, if present."""

    project_file_path: Path | None = find_project_file(path)
    if project_file_path is None:
        return None

    return load_project_yaml(project_file_path)
