from dataclasses import dataclass

from streambuild.cli.build.models import BuildProtectionRequirement


@dataclass(frozen=True)
class DirectBuildAuditSelectionTestCase:
    description: str
    audit_refs_by_name: tuple[tuple[str, tuple[str, ...]], ...]
    execution_model_names: frozenset[str]
    full_build: bool
    expected_audit_names: tuple[str, ...]


@dataclass(frozen=True)
class BuildConfirmationTestCase:
    description: str
    protection_requirements: tuple[BuildProtectionRequirement, ...]
    auto_approve: bool
    confirmations: tuple[str, ...]
    input_response: str | None
    expected_confirmed: bool
    expected_stderr_fragment: str
