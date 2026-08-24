"""CLI destruction command inputs."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from streambuild.executor.destruction.types import DestructionOperation


@dataclass(frozen=True, repr=False)
class DestructionCommandOptions:
    operation: DestructionOperation
    pipelines_root: Path
    project_dir: Path
    selected_target: str
    database: str | None
    selectors: tuple[str, ...]
    control_store_url: str
    cli_variables: tuple[tuple[str, object], ...] = ()
    environment: Mapping[str, str] | None = None
