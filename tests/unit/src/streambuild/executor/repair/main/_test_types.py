from dataclasses import dataclass

from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterStableBinding
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult


@dataclass(frozen=True)
class RepairBindingTestCase:
    description: str
    request: RepairActiveViewRequest
    expected_binding_request: AdapterBindingReplacementRequest
    expected_result: RepairActiveViewResult


@dataclass(frozen=True)
class RepairCapabilityTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class RepairBindingResultTestCase:
    description: str
    request: RepairActiveViewRequest
    returned_bindings: tuple[AdapterStableBinding, ...]
    expected_error_fragment: str
