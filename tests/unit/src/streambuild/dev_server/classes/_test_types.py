from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCancellationStateTestCase:
    description: str
    invocation_id: str
    expected_cancel_status: str
    expected_force_available: bool


@dataclass(frozen=True)
class BuildStartTestCase:
    description: str
    selector: str
    expected_status: str
    expected_running: bool


@dataclass(frozen=True)
class KafkaLagSnapshotTestCase:
    description: str
    partition_ids: frozenset[int]
    committed_offsets: tuple[tuple[int, int], ...]
    end_offsets: tuple[tuple[int, int], ...]
    expected_total_messages: int | None
    expected_partition_lags: tuple[int | None, ...]


@dataclass(frozen=True)
class AuditScheduleCalculationTestCase:
    description: str
    status_payloads: tuple[dict[str, object], ...]
    anchors_by_model: dict[str, str]
    warmup_anchor: str | None
    eligible_at: str | None
    warmup_eligible: bool
    materialization_outcome: str | None
    expected_scheduler_state: str
    expected_state: str
    expected_scheduled_for: str
    warehouse_now: str = "2026-08-08 12:00:00.000"


@dataclass(frozen=True)
class AuditSchedulerBackoffTestCase:
    description: str
    error_message: str
    expected_initial_backoff_seconds: float
    expected_result_count_after_recovery: int


@dataclass(frozen=True)
class AuditSchedulerActiveRunTestCase:
    description: str
    active_runs: tuple[dict[str, object], ...]
    latest_applied_at: str | None
    expected_payload_reads: int


@dataclass(frozen=True)
class AuditSchedulerLocalRaceTestCase:
    description: str
    expected_feed_reads: int


@dataclass(frozen=True)
class KafkaTopicsSnapshotTestCase:
    description: str
    metadata: tuple[dict, ...]
    expected_topics: tuple[tuple[str, int, int, bool], ...]


@dataclass(frozen=True)
class WarehouseRuntimeRecoveryTestCase:
    description: str
    failure_message: str
    expected_attempts: int
    expected_state: str
