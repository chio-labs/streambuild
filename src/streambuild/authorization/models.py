"""Immutable operational authorization inputs and decisions."""

from dataclasses import dataclass

from streambuild.auth.models import AuthenticatedRequest
from streambuild.authorization.types import AuthorizationReason
from streambuild.compiler.access.models import CompiledAccessPolicy
from streambuild.compiler.access.types import GrantScope, Permission


@dataclass(frozen=True)
class AuthorizationRequest:
    """Authoritative identity, policy, and resolved operation scope."""

    authenticated: AuthenticatedRequest
    permission: Permission
    project_name: str
    target_name: str | None
    grant_scope: GrantScope | None
    affected_pipelines: tuple[str, ...]
    policy: CompiledAccessPolicy | None


@dataclass(frozen=True)
class AuthorizationDecision:
    """Explainable allow or deny result from centralized evaluation."""

    allowed: bool
    reason: AuthorizationReason
    permission: Permission
    project_name: str
    target_name: str | None
    affected_pipelines: tuple[str, ...]
    matched_roles: tuple[str, ...] = ()
    missing_pipelines: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilityRequest:
    """Identity and policy inputs for one effective-capability summary."""

    authenticated: AuthenticatedRequest
    project_name: str
    target_name: str | None
    pipeline_names: tuple[str, ...]
    policy: CompiledAccessPolicy | None


@dataclass(frozen=True)
class EffectiveCapabilities:
    """UI-facing effective operation permissions for one user."""

    system_admin: bool
    project_name: str
    target_name: str | None
    permissions: tuple[Permission, ...]
    pipeline_permissions: tuple[tuple[Permission, tuple[str, ...]], ...]
    stale_roles: tuple[str, ...] = ()
