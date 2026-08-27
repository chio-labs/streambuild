"""Build development UI snapshots from Kafka responses."""

from collections.abc import Mapping, Sequence
from typing import cast

from streambuild.dev_server.models import (
    KafkaLagSnapshot,
    KafkaPartitionLag,
    KafkaTopicInfo,
    KafkaTopicsSnapshot,
)


def build_kafka_lag_snapshot(
    *,
    partition_ids: frozenset[int],
    committed_offsets: Mapping[int, int],
    end_offsets: Mapping[int, int],
) -> KafkaLagSnapshot:
    """Build exact lag, leaving totals unknown when a non-empty partition has no commit."""

    partitions: list[KafkaPartitionLag] = []
    total_messages: int = 0
    complete: bool = True
    if not partition_ids:
        return KafkaLagSnapshot(total_messages=None, partitions=())
    for partition in sorted(partition_ids):
        end_offset: int = end_offsets[partition]
        committed_offset: int | None = committed_offsets.get(partition)
        lag_messages: int | None
        if committed_offset is None and end_offset == 0:
            lag_messages = 0
        elif committed_offset is None:
            lag_messages = None
            complete = False
        else:
            lag_messages = max(0, end_offset - committed_offset)
        if lag_messages is not None:
            total_messages += lag_messages
        partitions.append(
            KafkaPartitionLag(
                partition=partition,
                committed_offset=committed_offset,
                end_offset=end_offset,
                lag_messages=lag_messages,
            )
        )
    return KafkaLagSnapshot(
        total_messages=total_messages if complete else None,
        partitions=tuple(partitions),
    )


def build_kafka_topics_snapshot(*, metadata: Sequence[Mapping[str, object]]) -> KafkaTopicsSnapshot:
    """Map raw kafka-python describe_topics metadata into the topic inventory."""

    topics: list[KafkaTopicInfo] = []
    for entry in metadata:
        partitions: object = entry.get("partitions", ())
        partition_list: tuple[Mapping[str, object], ...] = tuple(
            cast("Mapping[str, object]", partition)
            for partition in (partitions if isinstance(partitions, list | tuple) else ())
            if isinstance(partition, Mapping)
        )
        replication_factor: int = 0
        for partition in partition_list:
            replicas: object = partition.get("replicas")
            if isinstance(replicas, list | tuple):
                replication_factor = max(replication_factor, len(replicas))
        topics.append(
            KafkaTopicInfo(
                name=str(entry.get("topic", "")),
                partition_count=len(partition_list),
                replication_factor=replication_factor,
                internal=bool(entry.get("is_internal", False)),
            )
        )
    return KafkaTopicsSnapshot(topics=tuple(sorted(topics, key=lambda topic: topic.name)))
