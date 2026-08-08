"""Entry resetting committed offsets for sources whose landing tables are being created."""

from __future__ import annotations

from kafka import KafkaAdminClient

from streambuild.adapter.models import AdapterManagedSource
from streambuild.compiler.compile.constants import (
    KAFKA_TABLE_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.executor.kafka_admin._helpers.offset_reset import reset_one_consumer_group
from streambuild.executor.kafka_admin.models import ConsumerGroupOffsetReset
from streambuild.executor.kafka_admin.types import KafkaAdminClientFactory
from streambuild.executor.population.models import (
    PopulationManagedSource,
    PopulationSourcePreparation,
)


def reset_fresh_landing_offsets(
    *,
    source_preparation: PopulationSourcePreparation,
    client_factory: KafkaAdminClientFactory = KafkaAdminClient,
) -> tuple[ConsumerGroupOffsetReset, ...]:
    """Reset committed offsets for every managed source gaining a fresh landing table."""

    created_relation_names: frozenset[str] = frozenset(source_preparation.created_relation_names)
    resets: list[ConsumerGroupOffsetReset] = []
    managed_source: PopulationManagedSource
    for managed_source in source_preparation.managed_sources:
        resource: AdapterManagedSource = managed_source.resource
        landing_relation_name: str = RAW_TABLE_NAME_PREFIX + resource.name.removeprefix(
            KAFKA_TABLE_NAME_PREFIX
        )
        if landing_relation_name not in created_relation_names:
            continue
        resets.append(
            reset_one_consumer_group(
                resource=resource,
                database=managed_source.database,
                landing_relation_name=landing_relation_name,
                client_factory=client_factory,
            )
        )
    return tuple(resets)
