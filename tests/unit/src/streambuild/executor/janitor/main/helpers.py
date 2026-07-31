from collections.abc import Iterator

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
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


class BindingRemovalRecordingAdapterConnection(RecordingAdapterConnection):
    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        result: AdapterBindingReplacementResult = super().replace_stable_bindings(request)
        removed_names: frozenset[tuple[str, str]] = frozenset(
            (removal.database, removal.logical_name) for removal in request.removals
        )
        self._managed_table_state = InspectedManagedTableState(
            active_bindings=tuple(
                filter(
                    lambda binding: (binding.database, binding.logical_name) not in removed_names,
                    self._managed_table_state.active_bindings,
                )
            ),
            physical_candidates=self._managed_table_state.physical_candidates,
        )
        return result
