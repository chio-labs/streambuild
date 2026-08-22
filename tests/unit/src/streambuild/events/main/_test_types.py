from dataclasses import dataclass

from streambuild.events.types import AuditTransition
from streambuild.executor.auditing.types import QualityResultStatus


@dataclass(frozen=True)
class AuditTransitionTestCase:
    description: str
    status: QualityResultStatus
    previous_status: QualityResultStatus | None
    expected_transition: AuditTransition


@dataclass(frozen=True)
class AuditSampleTestCase:
    description: str
    payload_json: str
    expected_column_names: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class NodeResultEventTestCase:
    description: str
    node_kind: str
    status: QualityResultStatus
    previous_status: QualityResultStatus | None
    expected_event_count: int
    expected_transitions: tuple[AuditTransition, ...] = ()


@dataclass(frozen=True)
class InvocationEventTestCase:
    description: str
    command: str
    expected_event_count: int
