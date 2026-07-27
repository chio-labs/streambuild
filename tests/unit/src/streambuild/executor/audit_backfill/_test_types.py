from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    InspectedManagedTableState,
)
from streambuild.executor.audit_backfill.types import AuditAssessment


@dataclass(frozen=True)
class ReadinessComparisonConstructionTestCase:
    description: str
    deployment_id: str
    inspected_state: InspectedManagedTableState
    observations: tuple[AdapterReadinessRootObservation, ...]
    expected_request: AdapterReadinessRequest
    expected_root_names: tuple[str, ...]
    expected_assessments: tuple[AuditAssessment, ...]
    expected_row_deltas: tuple[int | None, ...]
    expected_lag_seconds: float
