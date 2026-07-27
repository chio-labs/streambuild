"""Runtime models for authored Python SQL macros."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from streambuild.compiler.discovery.main._immutable_config_pairs import immutable_config_pairs
from streambuild.compiler.macros.types import MacroFunction


@dataclass(frozen=True)
class LoadedMacro:
    """One registered authored Python macro."""

    name: str
    file_path: Path
    relative_path: Path
    source: str
    definition_line: int
    function: MacroFunction


@dataclass(frozen=True, repr=False)
class MacroRegistry:
    """One deeply immutable invocation-scoped macro registry."""

    macros: Mapping[str, LoadedMacro] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "macros", MappingProxyType(dict(self.macros)))


@dataclass(frozen=True, repr=False)
class MacroContext:
    """Connection-free immutable context optionally injected into macros."""

    adapter_name: str
    dialect: str
    target_name: str | None
    database: str | None
    schema: str | None
    virtual_environments: bool
    variables: Mapping[str, object]

    def __post_init__(self) -> None:
        frozen_variables: tuple[tuple[str, object], ...] = immutable_config_pairs(
            tuple(self.variables.items())
        )
        object.__setattr__(self, "variables", MappingProxyType(dict(frozen_variables)))
