"""Runtime models for authored Python SQL macros."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class LoadedMacro:
    """One registered authored Python macro."""

    name: str
    file_path: Path
    module: ModuleType
    function: Any
