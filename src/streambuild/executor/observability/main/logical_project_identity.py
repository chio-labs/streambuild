"""Stable logical project identity across release-directory changes."""

from pathlib import Path


def logical_project_identity(*, project_dir: Path) -> str:
    """Use the project directory name, not its release-specific absolute path."""

    return project_dir.resolve().name
