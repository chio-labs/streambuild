"""SQL audit discovery models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streambuild.compiler.audit_discovery.types import AuditAttachmentKind
from streambuild.compiler.quality.models import QualityNodeIdentity


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
    attachment_kind: AuditAttachmentKind | str = AuditAttachmentKind.STANDALONE
    attached_model: str | None = None
    attached_column: str | None = None
    quality_identity: QualityNodeIdentity | None = None
    severity_is_explicit: bool = False
    cadence_seconds: int | None = None
    warmup_seconds: int = 0
    scheduled: bool = False
    cadence_seconds_override: int | None = None
    warmup_seconds_override: int | None = None
    scheduled_override: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attachment_kind", AuditAttachmentKind(self.attachment_kind))


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
    severity_is_explicit: bool = False
    cadence_seconds_override: int | None = None
    warmup_seconds_override: int | None = None
    scheduled_override: bool | None = None
