from dataclasses import dataclass

from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult


@dataclass(frozen=True)
class RepairBindingTestCase:
    description: str
    request: RepairActiveViewRequest
    expected_statement: str
    expected_result: RepairActiveViewResult


@dataclass(frozen=True)
class RepairCapabilityTestCase:
    description: str
    expected_error_fragment: str
