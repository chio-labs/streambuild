import pytest

from streambuild.dev_server.classes.kafka_topic_reader import build_kafka_topics_snapshot
from streambuild.dev_server.models import KafkaTopicsSnapshot
from tests.unit.src.streambuild.dev_server.classes._test_types import KafkaTopicsSnapshotTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        KafkaTopicsSnapshotTestCase(
            description="maps topics with partitions, replication, and internal flags sorted",
            metadata=(
                {
                    "topic": "source.orders",
                    "is_internal": False,
                    "partitions": [
                        {"partition": 0, "replicas": [1, 2]},
                        {"partition": 1, "replicas": [2, 3]},
                    ],
                },
                {
                    "topic": "__consumer_offsets",
                    "is_internal": True,
                    "partitions": [{"partition": 0, "replicas": [1]}],
                },
            ),
            expected_topics=(
                ("__consumer_offsets", 1, 1, True),
                ("source.orders", 2, 2, False),
            ),
        ),
        KafkaTopicsSnapshotTestCase(
            description="tolerates topics without partition metadata",
            metadata=({"topic": "empty.topic", "is_internal": False, "partitions": []},),
            expected_topics=(("empty.topic", 0, 0, False),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broker_metadata_when_building_snapshot_then_maps_topic_inventory(
    test_case: KafkaTopicsSnapshotTestCase,
) -> None:
    snapshot: KafkaTopicsSnapshot = build_kafka_topics_snapshot(metadata=test_case.metadata)

    assert (
        tuple(
            (topic.name, topic.partition_count, topic.replication_factor, topic.internal)
            for topic in snapshot.topics
        )
        == test_case.expected_topics
    )
