"""Test-case models for operational authorization."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from streambuild.auth.classes.control_store import ControlStore
from streambuild.authorization.models import AuthorizationRequest
from streambuild.authorization.types import AuthorizationReason

type AuthorizationScenario = tuple[ControlStore, AuthorizationRequest]


class AuthorizationScenarioBuilder(Protocol):
    """Build one ready-to-evaluate operation and its store."""

    def __call__(self, *, tmp_path: Path) -> AuthorizationScenario: ...


@dataclass(frozen=True)
class AuthorizationTestCase:
    """Expected result for one authorization scenario builder."""

    description: str
    build_scenario: AuthorizationScenarioBuilder
    expected_allowed: bool
    expected_reason: AuthorizationReason
    expected_roles: tuple[str, ...] = ()
    expected_missing_pipelines: tuple[str, ...] = ()
