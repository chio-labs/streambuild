"""Resolve the project-local default control-store URL."""

from pathlib import Path


def default_control_store_url(*, project_dir: Path) -> str:
    """Return the deterministic project-local SQLite control-store URL."""

    database_path: Path = (project_dir / ".streambuild" / "control.db").resolve()
    return f"sqlite:///{database_path}"
