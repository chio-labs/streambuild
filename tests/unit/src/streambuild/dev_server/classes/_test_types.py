from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCancellationStateTestCase:
    description: str
    invocation_id: str
    expected_cancel_status: str
    expected_force_available: bool


@dataclass(frozen=True)
class KafkaLagSnapshotTestCase:
    description: str
    partition_ids: frozenset[int]
    committed_offsets: tuple[tuple[int, int], ...]
    end_offsets: tuple[tuple[int, int], ...]
    expected_total_messages: int | None
    expected_partition_lags: tuple[int | None, ...]
