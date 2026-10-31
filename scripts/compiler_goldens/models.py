"""Captured compiler outputs for one corpus project."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilerCapture:
    project: str
    exit_code: int
    definitions: object
    stdout: tuple[str, ...]
    stderr: tuple[str, ...]
    artifacts: dict[str, object]
