"""Helpers for access-policy compiler tests."""

from pathlib import Path

from streambuild.compiler.discovery.models import DiscoveredProjectFile


def access_source_file(*, tmp_path: Path, contents: str) -> DiscoveredProjectFile:
    """Build a retained root access file without filesystem I/O."""

    path: Path = tmp_path / "access.yml"
    return DiscoveredProjectFile(
        file_path=path, relative_path=Path("access.yml"), contents=contents
    )
