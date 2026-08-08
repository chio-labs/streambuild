"""Project macro source file discovery."""

from pathlib import Path

from streambuild.compiler.discovery.constants import PYTHON_PACKAGE_INITIALIZER_FILE_NAME
from streambuild.compiler.discovery.models import DiscoveredProjectFile


def discover_macro_files(*, project_dir: Path) -> tuple[DiscoveredProjectFile, ...]:
    """Read public project macro modules once in stable path order."""

    return tuple(
        DiscoveredProjectFile(
            file_path=path,
            relative_path=path.relative_to(project_dir),
            contents=path.read_text(encoding="utf-8"),
        )
        for path in sorted((project_dir / "macros").rglob("*.py"))
        if _is_public_macro_file(path=path, project_dir=project_dir)
    )


def _is_public_macro_file(*, path: Path, project_dir: Path) -> bool:
    relative_path: Path = path.relative_to(project_dir)
    return path.name != PYTHON_PACKAGE_INITIALIZER_FILE_NAME and not any(
        part.startswith("_") for part in relative_path.parts
    )
