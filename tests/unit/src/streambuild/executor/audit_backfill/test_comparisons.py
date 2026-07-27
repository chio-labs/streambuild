import pytest

from streambuild.adapter.models import (
    AdapterReadinessRequest,
    AdapterReadinessRootObservation,
    AdapterReadinessRootRequest,
    AdapterReadinessScalarSummary,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
)
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.executor.audit_backfill._helpers.comparisons import build_root_audit_results
from streambuild.executor.audit_backfill.models import RootAuditResult
from streambuild.executor.audit_backfill.types import AuditAssessment
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.audit_backfill._test_types import (
    ReadinessComparisonConstructionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadinessComparisonConstructionTestCase(
            description="correlates reordered neutral observations with their requested roots",
            deployment_id="20260726T180000Z_ab12cd",
            inspected_state=InspectedManagedTableState(
                active_bindings=(
                    InspectedActiveTableBinding(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        physical_name="tbl__orders_enriched__20260726T170000Z_prev01",
                    ),
                ),
                physical_candidates=(
                    InspectedPhysicalTableCandidate(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        physical_name="tbl__orders_enriched__20260726T180000Z_ab12cd",
                    ),
                    InspectedPhysicalTableCandidate(
                        database="analytics",
                        logical_name="tbl__payments_enriched",
                        physical_name="tbl__payments_enriched__20260726T180000Z_ab12cd",
                    ),
                ),
            ),
            observations=(
                AdapterReadinessRootObservation(
                    root=AdapterReadinessRootRequest(
                        database="analytics",
                        logical_name="tbl__payments_enriched",
                        staged_relation_name="tbl__payments_enriched__20260726T180000Z_ab12cd",
                        active_exists=False,
                    ),
                    staged_exists=True,
                    active_row_count=None,
                    staged_row_count=10,
                    replay_source_name="raw__payments",
                    replay_source_row_count=10,
                    replay_boundary_mode=AdapterReplayBoundaryMode.TIMESTAMP,
                    offset_summary=None,
                    scalar_summary=None,
                ),
                AdapterReadinessRootObservation(
                    root=AdapterReadinessRootRequest(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        staged_relation_name="tbl__orders_enriched__20260726T180000Z_ab12cd",
                        active_exists=True,
                    ),
                    staged_exists=True,
                    active_row_count=41,
                    staged_row_count=42,
                    replay_source_name="raw__orders",
                    replay_source_row_count=42,
                    replay_boundary_mode=AdapterReplayBoundaryMode.TIMESTAMP,
                    offset_summary=None,
                    scalar_summary=AdapterReadinessScalarSummary(
                        active_min_value="2026-07-26 17:00:00.000",
                        active_max_value="2026-07-26 17:59:59.000",
                        staged_min_value="2026-07-26 17:00:00.000",
                        staged_max_value="2026-07-26 18:00:00.000",
                        lag_seconds=-1.0,
                    ),
                ),
            ),
            expected_request=AdapterReadinessRequest(
                roots=(
                    AdapterReadinessRootRequest(
                        database="analytics",
                        logical_name="tbl__orders_enriched",
                        staged_relation_name="tbl__orders_enriched__20260726T180000Z_ab12cd",
                        active_exists=True,
                    ),
                    AdapterReadinessRootRequest(
                        database="analytics",
                        logical_name="tbl__payments_enriched",
                        staged_relation_name="tbl__payments_enriched__20260726T180000Z_ab12cd",
                        active_exists=False,
                    ),
                )
            ),
            expected_root_names=("tbl__orders_enriched", "tbl__payments_enriched"),
            expected_assessments=(AuditAssessment.READY, AuditAssessment.READY),
            expected_row_deltas=(1, None),
            expected_lag_seconds=-1.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_staged_state_when_building_readiness_then_adapter_request_and_policy_are_neutral(
    test_case: ReadinessComparisonConstructionTestCase,
) -> None:
    connection: RecordingAdapterConnection = RecordingAdapterConnection(
        readiness_observations=test_case.observations
    )

    results: tuple[RootAuditResult, ...] = build_root_audit_results(
        client=connection,
        default_database="analytics",
        deployment_id=test_case.deployment_id,
        inspected_state=test_case.inspected_state,
    )

    assert connection.readiness_requests == [test_case.expected_request]
    assert tuple(result.root_key.name for result in results) == test_case.expected_root_names
    assert tuple(result.assessment for result in results) == test_case.expected_assessments
    assert tuple(result.row_delta for result in results) == test_case.expected_row_deltas
    assert results[0].scalar_catchup_summary is not None
    assert results[0].scalar_catchup_summary.lag_seconds == test_case.expected_lag_seconds
