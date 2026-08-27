import uuid
from contextlib import ExitStack

import pytest
from kafka import KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.structs import OffsetAndMetadata

from streambuild.compiler.discovery.models import KafkaSettings
from streambuild.dev_server.classes.kafka_lag_collector import KafkaLagCollector
from streambuild.dev_server.classes.kafka_topic_collector import KafkaTopicCollector
from streambuild.dev_server.models import KafkaLagSnapshot, KafkaTopicsSnapshot
from tests.e2e.src.streambuild.conftest import E2EKafkaConnectionSettings
from tests.e2e.src.streambuild.dev_server._test_types import KafkaReaderReuseE2ETestCase


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        KafkaReaderReuseE2ETestCase(
            description="retained clients remain usable",
            consumer_group="streambuild-reader-test",
            expected_lag=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_live_broker_when_reading_repeatedly_then_retained_clients_remain_usable(
    test_case: KafkaReaderReuseE2ETestCase,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
) -> None:
    bootstrap_server: str = e2e_kafka_connection_settings.bootstrap_server
    topic: str = f"streambuild-reader-{uuid.uuid4().hex}"
    with ExitStack() as cleanup:
        admin: KafkaAdminClient = KafkaAdminClient(bootstrap_servers=bootstrap_server)
        cleanup.callback(admin.close)
        admin.create_topics(
            new_topics=[NewTopic(name=topic, num_partitions=1, replication_factor=1)]
        )
        cleanup.callback(admin.delete_topics, topics=[topic])
        partition: TopicPartition = TopicPartition(topic, 0)
        consumer: KafkaConsumer = KafkaConsumer(
            bootstrap_servers=bootstrap_server,
            group_id=f"{test_case.consumer_group}_default",
            enable_auto_commit=False,
        )
        try:
            consumer.assign([partition])
            consumer.commit(offsets={partition: OffsetAndMetadata(0, "")})
        finally:
            consumer.close()
        kafka: KafkaSettings = KafkaSettings(
            broker_list=bootstrap_server,
            topic=topic,
            consumer_group=test_case.consumer_group,
        )
        topic_collector: KafkaTopicCollector = KafkaTopicCollector()
        cleanup.callback(topic_collector.close)
        lag_collector: KafkaLagCollector = KafkaLagCollector()
        cleanup.callback(lag_collector.close)
        first_topics: KafkaTopicsSnapshot = topic_collector(kafka=kafka)
        second_topics: KafkaTopicsSnapshot = topic_collector(kafka=kafka)
        first_lag: KafkaLagSnapshot = lag_collector(kafka=kafka, database="default")
        second_lag: KafkaLagSnapshot = lag_collector(kafka=kafka, database="default")

        assert topic in {item.name for item in first_topics.topics}
        assert first_topics == second_topics
        assert first_lag.total_messages == test_case.expected_lag
        assert first_lag == second_lag


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
