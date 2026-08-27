from collections.abc import Callable
from typing import cast

import pytest
from kafka import KafkaAdminClient, KafkaConsumer, TopicPartition
from kafka.structs import OffsetAndMetadata

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server._helpers.broker.client import kafka_client_key
from streambuild.dev_server._helpers.broker.snapshots import build_kafka_lag_snapshot
from streambuild.dev_server.classes.kafka_lag_collector import KafkaLagCollector
from streambuild.dev_server.models import KafkaLagSnapshot
from tests.unit.src.streambuild.dev_server.classes._test_types import (
    KafkaClientReuseTestCase,
    KafkaCredentialIsolationTestCase,
    KafkaLagSnapshotTestCase,
)


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


@pytest.mark.parametrize(
    "test_case",
    [
        KafkaClientReuseTestCase(
            description="reuses one lag client pair",
            broker_list="broker:9092",
            expected_client_count=1,
            expected_query_count=2,
            expected_close_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_topics_when_collecting_lag_then_reuses_and_closes_broker_clients(
    test_case: KafkaClientReuseTestCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admins: list[_FakeAdminClient] = []
    consumers: list[_FakeConsumer] = []

    def admin_factory(**_config: object) -> _FakeAdminClient:
        admin: _FakeAdminClient = _FakeAdminClient()
        admins.append(admin)
        return admin

    def consumer_factory(**_config: object) -> _FakeConsumer:
        consumer: _FakeConsumer = _FakeConsumer()
        consumers.append(consumer)
        return consumer

    collector: KafkaLagCollector = KafkaLagCollector(
        admin_factory=cast("Callable[..., KafkaAdminClient]", admin_factory),
        consumer_factory=cast("Callable[..., KafkaConsumer]", consumer_factory),
    )
    first_kafka: KafkaSettings = KafkaSettings(
        broker_list=test_case.broker_list,
        topic="source.orders",
        consumer_group="streambuild-orders",
    )
    second_kafka: KafkaSettings = KafkaSettings(
        broker_list=test_case.broker_list,
        topic="source.prices",
        consumer_group="streambuild-prices",
    )

    first: KafkaLagSnapshot = collector(kafka=first_kafka, database="default")
    second: KafkaLagSnapshot = collector(kafka=second_kafka, database="default")
    collector.close()

    assert first.total_messages == 5
    assert second.total_messages == 5
    assert len(admins) == test_case.expected_client_count
    assert len(consumers) == test_case.expected_client_count
    assert admins[0].offset_calls == test_case.expected_query_count
    assert consumers[0].end_offset_calls == test_case.expected_query_count
    assert admins[0].close_calls == test_case.expected_close_count
    assert consumers[0].close_calls == test_case.expected_close_count
    assert (
        "Kafka lag clients opened brokers=broker:9092 opened_pairs=1 closed_pairs=0 "
        "active_pairs=1" in caplog.text
    )
    assert "Kafka lag clients reused brokers=broker:9092 reads=2" in caplog.text
    assert (
        "Kafka lag clients closed reads=2 opened_pairs=1 closed_pairs=1 active_pairs=0"
        in caplog.text
    )


class _FakeAdminClient:
    def __init__(self) -> None:
        self.offset_calls = 0
        self.close_calls = 0

    def list_consumer_group_offsets(
        self, _consumer_group: str
    ) -> dict[TopicPartition, OffsetAndMetadata]:
        self.offset_calls += 1
        topic: str = "source.orders" if self.offset_calls == 1 else "source.prices"
        return {TopicPartition(topic, 0): OffsetAndMetadata(5, "")}

    def close(self) -> None:
        self.close_calls += 1


class _FakeConsumer:
    def __init__(self) -> None:
        self.end_offset_calls = 0
        self.close_calls = 0

    def partitions_for_topic(self, _topic: str) -> set[int]:
        return {0}

    def end_offsets(self, partitions: tuple[TopicPartition, ...]) -> dict[TopicPartition, int]:
        self.end_offset_calls += 1
        return {partitions[0]: 10}

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.parametrize(
    "test_case",
    [
        KafkaCredentialIsolationTestCase(
            description="separates SASL usernames",
            first_username="first",
            second_username="second",
            expected_isolated=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_different_credentials_when_keying_clients_then_keeps_connections_isolated(
    test_case: KafkaCredentialIsolationTestCase,
) -> None:
    first: KafkaSettings = KafkaSettings(
        broker_list="broker:9092",
        topic="source.orders",
        settings={"kafka_sasl_username": test_case.first_username},
    )
    second: KafkaSettings = KafkaSettings(
        broker_list="broker:9092",
        topic="source.orders",
        settings={"kafka_sasl_username": test_case.second_username},
    )

    assert (kafka_client_key(kafka=first) != kafka_client_key(kafka=second)) is (
        test_case.expected_isolated
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
