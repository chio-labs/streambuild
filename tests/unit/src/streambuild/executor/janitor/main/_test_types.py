from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterRelationCleanupRequest,
    InspectedManagedTableState,
)
from streambuild.executor.janitor.models import JanitorApplyResult, JanitorRequest


@dataclass(frozen=True)
class JanitorAdapterCleanupTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    managed_table_state: InspectedManagedTableState
    request: JanitorRequest
    expected_cleanup_request: AdapterRelationCleanupRequest
    expected_result: JanitorApplyResult


@dataclass(frozen=True)
class JanitorCleanupResultTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    request: JanitorRequest
    returned_relation_names: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class JanitorUnsafeMappingTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    request: JanitorRequest
    expected_deletable: bool
    expected_reason: str


@dataclass(frozen=True)
class JanitorConcurrentActivationTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    managed_states: tuple[InspectedManagedTableState, ...]
    request: JanitorRequest
    expected_error_fragment: str
