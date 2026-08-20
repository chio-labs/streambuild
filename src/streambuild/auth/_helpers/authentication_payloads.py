"""Serialize authentication and account-domain models for HTTP responses."""

from streambuild.auth.models import (
    AccountAuditRecord,
    AuthenticatedRequest,
    AuthSettings,
    Principal,
    ProjectRoleAssignment,
    UserAccount,
)
from streambuild.auth.types import AuthenticationMode, AuthenticationSource


def authentication_config_payload(*, settings: AuthSettings) -> dict[str, object]:
    """Serialize browser-visible authentication configuration."""

    return {
        "mode": settings.mode,
        "loginRequired": settings.mode == AuthenticationMode.PASSWORD,
        "proxyLogoutUrl": settings.proxy_logout_url,
    }


def authenticated_payload(
    *, authenticated: AuthenticatedRequest, mode: AuthenticationMode
) -> dict[str, object]:
    """Serialize one authenticated request context."""

    principal: Principal = authenticated.principal
    return {
        "mode": mode,
        "user": {
            "id": str(principal.user_id),
            "username": principal.username,
            "displayName": principal.display_name,
            "email": principal.email,
            "authenticationSource": principal.authentication_source,
        },
        "roles": list(authenticated.roles),
        "csrfToken": authenticated.csrf_token,
    }


def user_payload(*, account: UserAccount) -> dict[str, object]:
    """Serialize one administrator-facing account record."""

    return {
        "id": str(account.user_id),
        "username": account.username,
        "displayName": account.display_name,
        "email": account.email,
        "active": account.is_active,
        "roles": list(account.roles),
        "authenticationSources": list(account.authentication_sources),
        "createdAt": account.created_at.isoformat(),
        "updatedAt": account.updated_at.isoformat(),
    }


def audit_payload(*, record: AccountAuditRecord) -> dict[str, object]:
    """Serialize one non-secret account audit record."""

    return {
        "operation": record.operation,
        "actorUserId": None if record.actor_user_id is None else str(record.actor_user_id),
        "affectedUserId": (
            None if record.affected_user_id is None else str(record.affected_user_id)
        ),
        "occurredAt": record.occurred_at.isoformat(),
        "details": record.details,
    }


def project_role_assignment_payload(*, assignment: ProjectRoleAssignment) -> dict[str, object]:
    """Serialize one audited project-role assignment."""

    return {
        "assignmentId": str(assignment.assignment_id),
        "userId": str(assignment.user_id),
        "projectName": assignment.project_name,
        "role": assignment.role_name,
        "targetName": assignment.target_name,
        "assignedBy": None if assignment.assigned_by is None else str(assignment.assigned_by),
        "assignedAt": assignment.assigned_at.isoformat(),
        "revokedBy": None if assignment.revoked_by is None else str(assignment.revoked_by),
        "revokedAt": None if assignment.revoked_at is None else assignment.revoked_at.isoformat(),
    }


def account_principal(*, account: UserAccount, source: AuthenticationSource) -> Principal:
    """Build a request principal from one account record."""

    return Principal(
        user_id=account.user_id,
        username=account.username,
        display_name=account.display_name,
        email=account.email,
        authentication_source=source,
    )
