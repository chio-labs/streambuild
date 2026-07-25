"""Runtime models for reconcile execution."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.shared.models import ObjectKey


@dataclass(frozen=True)
class ReconcileCandidate:
    key: ObjectKey
    target_key: ObjectKey
    target_name: str
    object_type: str


@dataclass(frozen=True)
class ReconcileRejectedTarget:
    target_key: ObjectKey
    target_name: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReconcilePreview:
    database: str
    reconcile_id: str
    eligible_records: tuple[ObjectStateRecord, ...]
    rejected_targets: tuple[ReconcileRejectedTarget, ...]


@dataclass(frozen=True)
class ReconcileResult:
    database: str
    reconcile_id: str
    reconciled_records: tuple[ObjectStateRecord, ...]
    rejected_targets: tuple[ReconcileRejectedTarget, ...]
