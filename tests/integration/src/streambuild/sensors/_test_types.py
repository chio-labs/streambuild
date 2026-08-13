from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryRoundtripTestCase:
    description: str
    expected_checkpoint: tuple[str, str]
    expected_step_status: str
    expected_step_result_json: str
    expected_override_status: str
    expected_first_lease: bool
    expected_competing_lease: bool


@dataclass(frozen=True)
class DispatchDeliveryTestCase:
    description: str
    expected_transition: str
    expected_event_id: str
    expected_tick_statuses: tuple[str, ...]


@dataclass(frozen=True)
class RedeliveryTestCase:
    description: str
    expected_event_ids: tuple[str, ...]
    expected_final_statuses: tuple[str, ...]
    expected_step_invocations: int


@dataclass(frozen=True)
class DeadLetterFlowTestCase:
    description: str
    expected_dead_letters_after_exhaustion: int
    expected_dead_letters_after_skip: int
    expected_handler_calls: int
