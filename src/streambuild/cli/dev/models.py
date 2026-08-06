"""Dev command option models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, repr=False)
class DevCommandOptions:
    """Parsed `stb dev` invocation options."""

    pipelines_root: Path
    database: str | None
    host: str
    port: int
    selected_target: str | None = None
    cli_variables: tuple[tuple[str, object], ...] = ()
    environment: Mapping[str, str] | None = None
    connection_host: str | None = None
    connection_port: int | None = None
    connection_username: str | None = None
    connection_password: str | None = None
