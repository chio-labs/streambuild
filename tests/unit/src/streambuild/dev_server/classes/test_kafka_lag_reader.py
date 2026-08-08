import pytest

from streambuild.dev_server.classes.kafka_lag_reader import build_kafka_lag_snapshot
from streambuild.dev_server.models import KafkaLagSnapshot
from tests.unit.src.streambuild.dev_server.classes._test_types import KafkaLagSnapshotTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        KafkaLagSnapshotTestCase(
            description="committed offsets produce exact partition and total lag",
            partition_ids=frozenset({0, 1}),
            committed_offsets=((0, 95), (1, 110)),
            end_offsets=((0, 100), (1, 125)),
            expected_total_messages=20,
            expected_partition_lags=(5, 15),
        ),
        KafkaLagSnapshotTestCase(
            description="empty uncommitted partition has zero lag",
            partition_ids=frozenset({0}),
            committed_offsets=(),
            end_offsets=((0, 0),),
            expected_total_messages=0,
            expected_partition_lags=(0,),
        ),
        KafkaLagSnapshotTestCase(
            description="nonempty uncommitted partition makes lag unavailable",
            partition_ids=frozenset({0, 1}),
            committed_offsets=((0, 90),),
            end_offsets=((0, 100), (1, 25)),
            expected_total_messages=None,
            expected_partition_lags=(10, None),
        ),
        KafkaLagSnapshotTestCase(
            description="missing topic metadata makes lag unavailable",
            partition_ids=frozenset(),
            committed_offsets=(),
            end_offsets=(),
            expected_total_messages=None,
            expected_partition_lags=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broker_offsets_when_building_snapshot_then_reports_only_exact_lag(
    test_case: KafkaLagSnapshotTestCase,
) -> None:
    snapshot: KafkaLagSnapshot = build_kafka_lag_snapshot(
        partition_ids=test_case.partition_ids,
        committed_offsets=dict(test_case.committed_offsets),
        end_offsets=dict(test_case.end_offsets),
    )

    assert snapshot.total_messages == test_case.expected_total_messages
    assert tuple(partition.lag_messages for partition in snapshot.partitions) == (
        test_case.expected_partition_lags
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
