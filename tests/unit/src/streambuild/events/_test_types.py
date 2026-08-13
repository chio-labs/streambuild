from dataclasses import dataclass

from streambuild.events.types import AuditTransition
from streambuild.executor.auditing.types import QualityResultStatus


@dataclass(frozen=True)
class NodeResultEventTestCase:
    description: str
    node_kind: str
    status: QualityResultStatus
    previous_status: QualityResultStatus | None
    expected_event_count: int
    expected_transitions: tuple[AuditTransition, ...] = ()


@dataclass(frozen=True)
class CatalogClosureTestCase:
    description: str
    expected_node_kinds: frozenset[str]
    expected_statuses: frozenset[str]
    expected_commands: frozenset[str]
    expected_transitions: frozenset[str]
