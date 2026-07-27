from collections.abc import Iterator

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterRelationCleanupRequest,
    AdapterRelationCleanupResult,
    InspectedManagedTableState,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class WrongCleanupAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        deployment_inventory: AdapterDeploymentInventory,
        returned_relation_names: tuple[str, ...],
    ) -> None:
        super().__init__(deployment_inventory=deployment_inventory)
        self._returned_relation_names: tuple[str, ...] = returned_relation_names

    def cleanup_relations(
        self, request: AdapterRelationCleanupRequest
    ) -> AdapterRelationCleanupResult:
        self.cleanup_requests.append(request)
        return AdapterRelationCleanupResult(relation_names=self._returned_relation_names)


class SequencedManagedStateAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        deployment_inventory: AdapterDeploymentInventory,
        managed_states: tuple[InspectedManagedTableState, ...],
    ) -> None:
        super().__init__(deployment_inventory=deployment_inventory)
        self._managed_states: Iterator[InspectedManagedTableState] = iter(managed_states)

    def inspect_managed_table_state(self, database: str) -> InspectedManagedTableState:
        del database
        return next(self._managed_states)
