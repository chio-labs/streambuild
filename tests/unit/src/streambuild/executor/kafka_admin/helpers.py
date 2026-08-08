from kafka.errors import GroupIdNotFoundError, KafkaError, NoError, NonEmptyGroupError

from streambuild.adapter.models import AdapterColumn, AdapterManagedSource
from streambuild.executor.kafka_admin.models import ConsumerGroupOffsetReset
from streambuild.executor.kafka_admin.types import KafkaAdminClientProtocol
from streambuild.executor.population.models import (
    PopulationManagedSource,
    PopulationSourcePreparation,
)

_DELETE_ERRORS_BY_NAME: dict[str, type[KafkaError]] = {
    "no_error": NoError,
    "group_id_not_found": GroupIdNotFoundError,
    "group_not_empty": NonEmptyGroupError,
}


def build_failure_reset(*, consumer_group: str, error: str) -> ConsumerGroupOffsetReset:
    return ConsumerGroupOffsetReset(
        consumer_group=consumer_group,
        landing_relation_name="raw__orders",
        deleted=False,
        error=error,
        notice=(
            "Could not reset committed offsets for consumer group "
            f"'{consumer_group}' ahead of creating raw__orders: {error}. If this landing table "
            "replaces a previous one, ingestion may resume from stale offsets; reset the group "
            "manually."
        ),
    )


class FakeKafkaAdminClient:
    """Records construction and returns canned delete responses."""

    def __init__(
        self,
        *,
        delete_results: tuple[tuple[str, str], ...],
        **config: object,
    ) -> None:
        self.config = config
        self.closed = False
        self.deleted_group_ids: list[str] = []
        self._delete_results = delete_results

    def delete_consumer_groups(self, group_ids: list[str]) -> list[tuple[str, object]]:
        self.deleted_group_ids.extend(group_ids)
        return [
            (group_id, _DELETE_ERRORS_BY_NAME[error_name])
            for group_id, error_name in self._delete_results
        ]

    def close(self) -> None:
        self.closed = True


class RecordingClientFactory:
    """Build fake admin clients and retain them for assertions."""

    def __init__(self, *, delete_results: tuple[tuple[str, str], ...] = ()) -> None:
        self.clients: list[FakeKafkaAdminClient] = []
        self._delete_results = delete_results

    def __call__(self, **config: object) -> FakeKafkaAdminClient:
        client: FakeKafkaAdminClient = FakeKafkaAdminClient(
            delete_results=self._delete_results,
            **config,
        )
        self.clients.append(client)
        return client


class FailingClientFactory:
    """Refuse construction like an unreachable broker."""

    def __init__(self, *, error: str) -> None:
        self._error = error

    def __call__(self, **config: object) -> KafkaAdminClientProtocol:
        del config
        raise ConnectionError(self._error)


class DeleteFailingKafkaAdminClient:
    """Raise from group deletion while recording closure."""

    def __init__(self, *, error: str) -> None:
        self.closed = False
        self._error = error

    def delete_consumer_groups(self, group_ids: list[str]) -> list[tuple[str, object]]:
        del group_ids
        raise RuntimeError(self._error)

    def close(self) -> None:
        self.closed = True


class DeleteFailingClientFactory:
    """Build one admin client whose delete request fails."""

    def __init__(self, *, error: str) -> None:
        self.client = DeleteFailingKafkaAdminClient(error=error)

    def __call__(self, **config: object) -> DeleteFailingKafkaAdminClient:
        del config
        return self.client


def build_orders_managed_source(
    *,
    broker_list: str = "kafka:9092",
    settings: tuple[tuple[str, str], ...] = (),
) -> AdapterManagedSource:
    return AdapterManagedSource(
        source_kind="kafka",
        name="kafka__orders",
        columns=(AdapterColumn(name="message", type="String"),),
        broker_list=broker_list,
        topic="source.orders",
        consumer_group="streambuild_orders_orders",
        format="JSONAsString",
        settings=settings,
    )


def build_source_preparation(
    *,
    created_relation_names: tuple[str, ...],
    broker_list: str = "kafka:9092",
    settings: tuple[tuple[str, str], ...] = (),
) -> PopulationSourcePreparation:
    return PopulationSourcePreparation(
        preserved_relation_names=(),
        created_relation_names=created_relation_names,
        landing_views=(),
        managed_sources=(
            PopulationManagedSource(
                resource=build_orders_managed_source(
                    broker_list=broker_list,
                    settings=settings,
                ),
                database="analytics",
            ),
        ),
    )
