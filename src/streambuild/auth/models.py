"""Typed authentication and account-domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from streambuild.auth.constants import ADMIN_ROLE
from streambuild.auth.exceptions import AuthConfigurationError
from streambuild.auth.types import AuthenticationMode, AuthenticationSource, UnknownUserPolicy


@dataclass(frozen=True)
class Principal:
    """Authenticated request identity, independent of authorization policy."""

    user_id: UUID
    username: str
    display_name: str | None
    email: str | None
    authentication_source: AuthenticationSource


@dataclass(frozen=True, repr=False)
class AuthSettings:
    """Server-runtime authentication and control-store settings."""

    mode: AuthenticationMode
    control_store_url: str
    username_header: str = "X-Mustard-User"
    display_name_header: str | None = None
    email_header: str | None = None
    unknown_user_policy: UnknownUserPolicy = UnknownUserPolicy.AUTO_PROVISION
    default_role: str = "viewer"
    session_cookie_name: str = "streambuild_session"
    session_ttl_seconds: int = 12 * 60 * 60
    session_cookie_secure: bool = True
    proxy_logout_url: str | None = None

    def __post_init__(self) -> None:
        if self.session_ttl_seconds <= 0:
            raise AuthConfigurationError("Session TTL must be positive")
        if (
            self.mode == AuthenticationMode.TRUSTED_PROXY
            and self.unknown_user_policy == UnknownUserPolicy.AUTO_PROVISION
            and self.default_role == ADMIN_ROLE
        ):
            raise AuthConfigurationError(
                "Trusted-proxy auto-provisioning cannot grant the admin role"
            )

    def __repr__(self) -> str:
        driver: str = self.control_store_url.partition(":")[0]
        return (
            "AuthSettings("
            f"mode={self.mode!r}, control_store_url='<redacted:{driver}>', "
            f"username_header={self.username_header!r}, "
            f"unknown_user_policy={self.unknown_user_policy!r}, "
            f"default_role={self.default_role!r})"
        )


@dataclass(frozen=True)
class UserAccount:
    """Persisted StreamBuild account without credential material."""

    user_id: UUID
    username: str
    display_name: str | None
    email: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    roles: tuple[str, ...] = ()
    authentication_sources: tuple[AuthenticationSource, ...] = ()


@dataclass(frozen=True)
class SessionCredentials:
    """One newly issued browser session; only the hash is persisted."""

    token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class ResolvedSession:
    """Active browser session and its authenticated principal."""

    principal: Principal
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedRequest:
    """Principal plus request-local account/session state."""

    principal: Principal
    roles: tuple[str, ...]
    csrf_token: str | None = None


@dataclass(frozen=True)
class AccountAuditRecord:
    """Non-secret account administration audit event."""

    operation: str
    actor_user_id: UUID | None
    affected_user_id: UUID | None
    occurred_at: datetime
    details: dict[str, object]


@dataclass(frozen=True)
class ProjectRoleAssignment:
    """Audited user membership in one project-authored operational role."""

    assignment_id: UUID
    user_id: UUID
    project_name: str
    role_name: str
    target_name: str | None
    assigned_by: UUID | None
    assigned_at: datetime
    revoked_by: UUID | None = None
    revoked_at: datetime | None = None


class LoginRequest(BaseModel):
    """Password-login request body."""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class CreateUserRequest(BaseModel):
    """Account-creation request body."""

    username: str
    displayName: str | None = None
    email: str | None = None
    authenticationSource: Literal["password", "trusted_proxy"]
    password: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["viewer"])


class UpdateUserRequest(BaseModel):
    """Account-profile and status update request body."""

    displayName: str | None = None
    email: str | None = None
    active: bool | None = None


class PasswordResetRequest(BaseModel):
    """Password-reset request body."""

    password: str


class RoleRequest(BaseModel):
    """Role-assignment request body."""

    role: str


class ProjectRoleRequest(BaseModel):
    """Project-role assignment request body; a null target means all targets."""

    projectName: str = Field(min_length=1, max_length=256)  # noqa: N815 - wire format
    role: str = Field(min_length=1, max_length=128)
    targetName: str | None = Field(default=None, max_length=128)  # noqa: N815 - wire format
