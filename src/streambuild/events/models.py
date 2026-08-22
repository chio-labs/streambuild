"""Event envelopes and the persisted observation rows they derive from."""

from __future__ import annotations

from dataclasses import dataclass

from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.events.types import AuditTransition, ObservedCommand
from streambuild.executor.auditing.types import QualityResultStatus


@dataclass(frozen=True)
class NodeResultObservation:
    """One persisted quality node result row viewed by the event catalog."""

    result_id: str
    invocation_id: str
    node_kind: QualityNodeKind
    node_name: str
    binding_key: str
    target_identity: str
    trigger: str
    status: QualityResultStatus
    severity: str | None
    failure_count: int
    completed_at: str
    scheduled_for: str | None
    payload_json: str
    error_message: str | None


@dataclass(frozen=True)
class InvocationObservation:
    """One persisted terminal invocation row viewed by the event catalog."""

    invocation_id: str
    command: str
    mode: str | None
    outcome: str
    exit_code: int
    target_identity: str
    deployment_id: str | None
    selected_node_count: int
    error_message: str | None
    completed_at: str


@dataclass(frozen=True)
class AuditCompleted:
    """One audit attempt reached a terminal status."""

    id: str
    audit_name: str
    status: QualityResultStatus
    previous_status: QualityResultStatus | None
    transition: AuditTransition
    severity: str | None
    failure_count: int
    target: str
    trigger: str
    completed_at: str
    binding_key: str
    invocation_id: str
    scheduled_for: str | None
    error_message: str | None
    sample_column_names: tuple[str, ...] = ()
    sample_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class RunCompleted:
    """One recorded command invocation reached a terminal outcome."""

    id: str
    command: ObservedCommand
    mode: str | None
    outcome: str
    exit_code: int
    target: str
    deployment_id: str | None
    selected_node_count: int
    error_message: str | None
    completed_at: str
