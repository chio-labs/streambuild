from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterDeploymentInventory,
    AdapterStableBinding,
    CatalogRelation,
    InspectedManagedTableState,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class WrongBindingAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        managed_table_state: InspectedManagedTableState,
        deployment_inventory: AdapterDeploymentInventory,
        relations: tuple[CatalogRelation, ...],
        returned_bindings: tuple[AdapterStableBinding, ...],
    ) -> None:
        super().__init__(
            managed_table_state=managed_table_state,
            deployment_inventory=deployment_inventory,
            relations=relations,
        )
        self._returned_bindings: tuple[AdapterStableBinding, ...] = returned_bindings

    def replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> AdapterBindingReplacementResult:
        self.binding_requests.append(request)
        return AdapterBindingReplacementResult(
            bindings=self._returned_bindings,
            per_relation_atomic_replace=self.capabilities.per_relation_atomic_replace,
            graph_atomic_publish=self.capabilities.graph_atomic_publish,
        )
