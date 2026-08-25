from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    CatalogRelation,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
)
from streambuild.executor.promotion.models import (
    DeploymentPromotionPreview,
    PublishRequest,
    PublishResult,
    RollbackPlan,
    RollbackRequest,
)


@dataclass(frozen=True)
class PromotionPreviewTestCase:
    description: str
    binding_request: AdapterBindingReplacementRequest
    active_bindings: tuple[InspectedActiveTableBinding, ...]
    expected_preview: DeploymentPromotionPreview


@dataclass(frozen=True)
class PromotionCandidateCompletenessTestCase:
    description: str
    partial_deployment_id: str
    complete_deployment_id: str
    expected_deployment_ids: tuple[str, ...]


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


@dataclass(frozen=True)
class RollbackResolutionSuccessTestCase:
    description: str
    request: RollbackRequest
    expected_plan: RollbackPlan


@dataclass(frozen=True)
class RollbackResolutionErrorTestCase:
    description: str
    request: RollbackRequest
    managed_table_state: InspectedManagedTableState
    expected_error_fragment: str
    relations: tuple[CatalogRelation, ...] = ()


@dataclass(frozen=True)
class RollbackInventoryErrorTestCase:
    description: str
    request: RollbackRequest
    inventory: AdapterDeploymentInventory
    managed_table_state: InspectedManagedTableState
    expected_error_fragment: str


@dataclass(frozen=True)
class RollbackPublicationOrderTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    expected_target_deployment_id: str
