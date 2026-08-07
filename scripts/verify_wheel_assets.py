"""Verify packaged development UI assets in the release wheel."""

from scripts.distribution.constants import DEFAULT_DISTRIBUTION_DIRECTORY
from scripts.distribution.main.verify_wheel_assets import verify_wheel_assets


def main() -> int:
    return verify_wheel_assets(distribution_dir=DEFAULT_DISTRIBUTION_DIRECTORY)


if __name__ == "__main__":
    raise SystemExit(main())
