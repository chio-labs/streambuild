"""Test-case models for access-policy compilation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessPolicyTestCase:
    """One valid authored access policy."""

    description: str
    contents: str
    pipeline_names: frozenset[str]
    expected_pipeline_names: tuple[str, ...]
    expected_permissions: tuple[str, ...]
    expected_scope: str


@dataclass(frozen=True)
class EquivalentAccessPoliciesTestCase:
    """Two authored policies with the same operational meaning."""

    description: str
    first_contents: str
    second_contents: str
    pipeline_names: frozenset[str]
    expected_fingerprints_equal: bool


@dataclass(frozen=True)
class MissingAccessPolicyTestCase:
    """One project with no authored access policy."""

    description: str
    pipeline_names: frozenset[str]
    expected_policy: None = None


@dataclass(frozen=True)
class InvalidAccessPolicyTestCase:
    """One authored policy expected to fail compilation."""

    description: str
    contents: str
    expected_message: str
    expected_line: int = 1
