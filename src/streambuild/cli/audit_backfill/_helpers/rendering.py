from __future__ import annotations

from pathlib import Path


def _display_path(*, file_path: Path, project_dir: Path | None) -> str:
    if project_dir is None:
        return str(file_path)
    try:
        return str(file_path.relative_to(project_dir))
    except ValueError:
        return str(file_path)
