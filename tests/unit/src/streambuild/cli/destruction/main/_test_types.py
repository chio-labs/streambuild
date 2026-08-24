from dataclasses import dataclass

from streambuild.auth.models import UserAccount


@dataclass(frozen=True)
class DestructionRunTestCase:
    description: str
    expected_exit_code: int
    expected_actor_id: str
    expected_actor_name: str
    expected_challenge_responses: tuple[str, ...]
    expected_analysis_count_after_replan: int


@dataclass(frozen=True)
class DestructionCancellationTestCase:
    description: str
    expected_exit_code: int
    expected_execution_count: int


@dataclass(frozen=True)
class DestructionAuthorizationTestCase:
    description: str
    account: UserAccount | None
    expected_error_fragment: str


@dataclass(frozen=True)
class DestructionReauthorizationTestCase:
    description: str
    refreshed_account: UserAccount
    expected_error_fragment: str
