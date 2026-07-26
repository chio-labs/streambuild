from dataclasses import dataclass


@dataclass(frozen=True)
class ExecuteDoctorIntegrationTestCase:
    description: str
    setup_kind: str
    active_view_target_deployment_id: str | None
    candidate_deployment_ids: tuple[str, ...]
    invalid_active_view_target_name: str | None
    expected_state_kind: str
    expected_active_deployment_id: str | None
    expected_candidate_deployment_ids: tuple[str, ...]
