from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterMetadataState,
    CatalogRelation,
    InspectedManagedTableState,
)
from streambuild.adapters.clickhouse._helpers.lifecycle import (
    render_clickhouse_stable_binding_replacement,
)
from streambuild.adapters.clickhouse._helpers.metadata import render_clickhouse_metadata_state
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class PublishWorkflowAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        managed_table_state: InspectedManagedTableState,
        deployment_inventory: AdapterDeploymentInventory,
        relations: tuple[CatalogRelation, ...],
    ) -> None:
        super().__init__(
            managed_table_state=managed_table_state,
            deployment_inventory=deployment_inventory,
            relations=relations,
        )

    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        return (f"CREATE DATABASE IF NOT EXISTS {database};",)

    def render_persist_metadata_state(
        self, *, database: str, state: AdapterMetadataState
    ) -> tuple[str, ...]:
        return render_clickhouse_metadata_state(database=database, state=state)

    def render_replace_stable_bindings(
        self, request: AdapterBindingReplacementRequest
    ) -> tuple[str, ...]:
        return render_clickhouse_stable_binding_replacement(
            connection=self,
            request=request,
        )
