"""Provider discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.providers import Provider


@dataclass(frozen=True)
class DiscoveredProvider:
    """A discovered project provider class and validated settings object."""

    file_path: Path
    relative_path: Path
    name: str
    provider_class: type[Provider]
    settings: Provider
