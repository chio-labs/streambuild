from dataclasses import dataclass


@dataclass(frozen=True)
class DirectBuildAuditSelectionTestCase:
    description: str
    audit_refs_by_name: tuple[tuple[str, tuple[str, ...]], ...]
    execution_model_names: frozenset[str]
    full_build: bool
    expected_audit_names: tuple[str, ...]
