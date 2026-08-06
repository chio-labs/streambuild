"""SQL audit discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoadedSqlAudit:
    """One discovered SQL audit file with validated metadata and refs."""

    file_path: Path
    query: str
    referenced_model_names: tuple[str, ...]
    severity: str = "error"
    description: str | None = None
    name: str | None = None
    audit_index: int = 1
    generic_definition_name: str | None = None


@dataclass(frozen=True)
class LoadedGenericSqlAuditDefinition:
    """One reusable generic SQL audit definition discovered from `audits/generic/`."""

    file_path: Path
    query: str
    raw_parameter_names: tuple[str, ...]
    quoted_parameter_names: tuple[str, ...]
    name: str


@dataclass(frozen=True)
class LoadedGenericSqlAuditInstance:
    """One schema-attached generic SQL audit before template rendering."""

    file_path: Path
    definition_name: str
    arguments: dict[str, object]
    name: str
    severity: str = "error"
    description: str | None = None
