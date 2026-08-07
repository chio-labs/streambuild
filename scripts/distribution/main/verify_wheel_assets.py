"""Verify that a built wheel contains the packaged development UI."""

from pathlib import Path
from zipfile import ZipFile

from scripts.distribution.constants import IMMUTABLE_APP_PREFIX, STATIC_INDEX_PATH
from scripts.distribution.exceptions import DistributionVerificationError


def verify_wheel_assets(*, distribution_dir: Path) -> int:
    """Verify the sole wheel's required UI assets and return a process exit code."""

    wheel_paths: tuple[Path, ...] = tuple(sorted(distribution_dir.glob("*.whl")))
    if len(wheel_paths) != 1:
        raise DistributionVerificationError(
            f"Expected exactly one wheel in {distribution_dir}, found {len(wheel_paths)}"
        )
    wheel_path: Path = wheel_paths[0]
    with ZipFile(wheel_path) as wheel_archive:
        archive_names: frozenset[str] = frozenset(wheel_archive.namelist())
    if STATIC_INDEX_PATH not in archive_names:
        raise DistributionVerificationError(
            f"Wheel is missing required UI asset: {STATIC_INDEX_PATH}"
        )
    if not any(name.startswith(IMMUTABLE_APP_PREFIX) for name in archive_names):
        raise DistributionVerificationError(
            f"Wheel is missing the UI application bundle under {IMMUTABLE_APP_PREFIX}"
        )
    return 0
