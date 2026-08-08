from dataclasses import dataclass


@dataclass(frozen=True)
class BoundedNodeResultTestCase:
    description: str
    payload_size: int
    error_size: int
    expected_payload_json: str
    expected_error_length: int


@dataclass(frozen=True)
class ObservationArtifactTestCase:
    description: str
    statements: tuple[str, ...]
    expected_workflow_sql: str
    expected_step_names: tuple[str, ...]
    expected_artifact_seen_before_execution: bool
