from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    CatalogRelation,
    InspectedManagedTableState,
)
from streambuild.executor.deployment.models import (
    DeploymentDiffRequest,
    DeploymentDiffResult,
)
from streambuild.executor.deployment.types import DeploymentDiffStatus


@dataclass(frozen=True)
class DeploymentDiffSuccessTestCase:
    description: str
    request: DeploymentDiffRequest
    expected_result: DeploymentDiffResult


@dataclass(frozen=True)
class DeploymentDiffErrorTestCase:
    description: str
    request: DeploymentDiffRequest
    expected_error_fragment: str


@dataclass(frozen=True)
class DeploymentDiffEndpointTestCase:
    description: str
    request: DeploymentDiffRequest
    expected_from_endpoint: str
    expected_to_endpoint: str


@dataclass(frozen=True)
class DeploymentDiffResolvedStatusTestCase:
    description: str
    request: DeploymentDiffRequest
    inventory: AdapterDeploymentInventory
    managed_state: InspectedManagedTableState
    relations: tuple[CatalogRelation, ...]
    row_counts_by_statement: dict[str, int]
    expected_statuses: tuple[DeploymentDiffStatus, ...]
    expected_statements: tuple[str, ...]
