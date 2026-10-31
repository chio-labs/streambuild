from dataclasses import dataclass


@dataclass(frozen=True)
class AuditBatchWorkTestCase:
    description: str
    expected_audit_count: int
