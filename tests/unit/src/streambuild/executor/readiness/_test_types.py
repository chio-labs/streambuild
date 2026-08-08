from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    InspectedManagedTableState,
)
from streambuild.executor.readiness.types import AuditAssessment


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


@dataclass(frozen=True)
class ReadinessThresholdTestCase:
    description: str
    maximum_lag_seconds: float
    minimum_staged_row_ratio: float
    active_row_count: int
    staged_row_count: int
    lag_seconds: float
    expected_assessment: AuditAssessment
