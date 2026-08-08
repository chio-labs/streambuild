from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterQueryResult,
    CatalogRelation,
    InspectedManagedTableState,
)
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class DeploymentDiffRecordingAdapterConnection(RecordingAdapterConnection):
    def __init__(
        self,
        *,
        relations: tuple[CatalogRelation, ...],
        managed_table_state: InspectedManagedTableState,
        deployment_inventory: AdapterDeploymentInventory,
        row_counts_by_statement: dict[str, int],
    ) -> None:
        super().__init__(
            relations=relations,
            managed_table_state=managed_table_state,
            deployment_inventory=deployment_inventory,
        )
        self._row_counts_by_statement: dict[str, int] = row_counts_by_statement

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return AdapterQueryResult(rows=((self._row_counts_by_statement[statement],),))
