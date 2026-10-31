"""Resolve the project-local default control-store URL."""

from pathlib import Path


def default_control_store_url(*, project_dir: Path) -> str:
    """Return the project-local SQLite URL, moving pre-rename `.streambuild/` state first."""

    state_dir: Path = (project_dir / ".sqltide").resolve()
    streambuild_state_dir: Path = (project_dir / ".streambuild").resolve()
    if not state_dir.exists() and streambuild_state_dir.is_dir():
        streambuild_state_dir.rename(state_dir)
    return f"sqlite:///{state_dir / 'control.db'}"
