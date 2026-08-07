from pathlib import Path
from zipfile import ZipFile


def write_wheel(*, distribution_dir: Path, wheel_name: str, archive_names: tuple[str, ...]) -> Path:
    wheel_path: Path = distribution_dir / wheel_name
    with ZipFile(wheel_path, mode="w") as wheel_archive:
        archive_name: str
        for archive_name in archive_names:
            wheel_archive.writestr(archive_name, b"asset")
    return wheel_path
