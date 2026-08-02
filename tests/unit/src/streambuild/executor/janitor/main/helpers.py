from collections.abc import Iterator

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterRelationCleanupRequest,
    InspectedManagedTableState,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


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


class JanitorWorkflowRecordingAdapterConnection(RecordingAdapterConnection):
    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        self.binding_requests.append(request)
        return tuple(
            f"DROP VIEW IF EXISTS {removal.database}.{removal.logical_name} SYNC;"
            for removal in request.removals
        )

    def render_cleanup_relations(self, request: AdapterRelationCleanupRequest) -> tuple[str, ...]:
        self.cleanup_requests.append(request)
        return tuple(
            f"DROP TABLE IF EXISTS {request.database}.{relation_name} SYNC;"
            for relation_name in request.relation_names
        )
