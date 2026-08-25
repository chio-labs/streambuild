from dataclasses import dataclass


@dataclass(frozen=True)
class DestructionIntegrationTestCase:
    description: str
    expected_destroy_outcome: str
    expected_reset_outcome: str
    expected_terminal_invocation_count: int


@dataclass(frozen=True)
class OwnershipIntegrationTestCase:
    description: str
    expected_error_match: str


@dataclass(frozen=True)
class VirtualHistoryIntegrationTestCase:
    description: str
    expected_reset_included_names: tuple[str, ...]
    expected_destroy_excluded_names: tuple[str, ...]


@dataclass(frozen=True)
class CompletionEventFailureIntegrationTestCase:
    description: str
    expected_outcome: str
    expected_residual_status: str
