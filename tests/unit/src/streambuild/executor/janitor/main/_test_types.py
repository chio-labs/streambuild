from dataclasses import dataclass

from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterDeploymentInventory,
    AdapterRelationCleanupRequest,
    InspectedManagedTableState,
)
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorRequest,
)


@dataclass(frozen=True)
class JanitorAdapterCleanupTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    managed_table_state: InspectedManagedTableState
    request: JanitorRequest
    expected_cleanup_request: AdapterRelationCleanupRequest
    expected_binding_request: AdapterBindingReplacementRequest
    expected_statements: tuple[str, ...]
    expected_result: JanitorApplyResult


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


@dataclass(frozen=True)
class JanitorRollbackSafetyTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    managed_table_state: InspectedManagedTableState
    preview_request: JanitorRequest
    apply_request: JanitorRequest
    expected_preview_states: tuple[tuple[str, bool, str], ...]
    expected_cleanup_request: AdapterRelationCleanupRequest
    expected_binding_request: AdapterBindingReplacementRequest
    expected_statements: tuple[str, ...]
    expected_result: JanitorApplyResult


@dataclass(frozen=True)
class JanitorUnavailableRollbackTestCase:
    description: str
    inventory: AdapterDeploymentInventory
    managed_table_state: InspectedManagedTableState
    request: JanitorRequest
    missing_deployment_id: str
    usable_deployment_id: str
    expected_usable_reason: str
