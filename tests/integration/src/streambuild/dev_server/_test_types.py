from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledAuditWarehouseTestCase:
    description: str
    expected_first_tick_count: int
    expected_later_tick_count: int
    expected_status: str
    expected_outcome: str
    expected_event_kinds: tuple[str, ...]


@dataclass(frozen=True)
class ScheduledAuditOutcomeTestCase:
    description: str
    severity: str
    audit_query: str
    expected_status: str
    expected_outcome: str


@dataclass(frozen=True)
class ScheduledAuditContentionTestCase:
    description: str
    expected_tick_counts: tuple[int, int]
    expected_claim_count: int
    expected_result_count: int
