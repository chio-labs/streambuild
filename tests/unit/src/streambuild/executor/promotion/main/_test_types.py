from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    CatalogRelation,
    InspectedManagedTableState,
)
from streambuild.executor.promotion.models import PublishRequest, PublishResult


@dataclass(frozen=True)
class PublishWorkflowTestCase:
    description: str
    request: PublishRequest
    managed_table_state: InspectedManagedTableState
    deployment_inventory: AdapterDeploymentInventory
    relations: tuple[CatalogRelation, ...]
    expected_statements: tuple[str, ...]
    expected_result: PublishResult


@dataclass(frozen=True)
class PublishCapabilityRejectionTestCase:
    description: str
    expected_error_fragment: str
