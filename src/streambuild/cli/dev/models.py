"""Dev command option models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DevCommandOptions:
    """Parsed `stb dev` invocation options."""

    pipelines_root: Path
    database: str | None
    host: str
    port: int
