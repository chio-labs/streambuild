from dataclasses import dataclass


@dataclass(frozen=True)
class AuditIdentityComparisonTestCase:
    description: str
    first_name: str
    first_query: str
    first_resolved_query: str
    first_severity: str
    second_name: str
    second_query: str
    second_resolved_query: str
    second_severity: str
    expected_binding_match: bool
    expected_definition_match: bool
    expected_execution_match: bool


@dataclass(frozen=True)
class QualityExecutionIdentityTestCase:
    description: str
    first_model_query: str
    second_model_query: str
    expected_binding_match: bool
    expected_definition_match: bool
    expected_execution_match: bool
