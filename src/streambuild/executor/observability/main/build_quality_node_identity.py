"""Construct one stable quality node identity."""

from pathlib import Path


def build_quality_node_identity(*, project_dir: Path, file_path: Path, node_index: int) -> str:
    """Return an identity independent of the project's checkout location."""

    resolved_project: Path = project_dir.resolve()
    resolved_file: Path = (
        file_path.resolve() if file_path.is_absolute() else (resolved_project / file_path).resolve()
    )
    relative_file: Path = resolved_file.relative_to(resolved_project)
    return f"{relative_file.as_posix()}:{node_index}"
