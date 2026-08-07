"""Distribution verification constants."""

from pathlib import Path

DEFAULT_DISTRIBUTION_DIRECTORY: Path = Path("dist")
STATIC_ASSET_PREFIX: str = "streambuild/dev_server/static/"
STATIC_INDEX_PATH: str = f"{STATIC_ASSET_PREFIX}index.html"
IMMUTABLE_APP_PREFIX: str = f"{STATIC_ASSET_PREFIX}_app/immutable/"
