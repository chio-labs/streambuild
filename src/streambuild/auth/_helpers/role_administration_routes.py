"""Register role assignment and account-audit administration routes."""

from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request

from streambuild.auth._helpers.authentication_payloads import (
    audit_payload,
    project_role_assignment_payload,
    user_payload,
)
from streambuild.auth._helpers.request_authentication import require_admin
from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.exceptions import (
    AccountConflictError,
    AccountNotFoundError,
    AccountValidationError,
)
from streambuild.auth.models import (
    AuthenticatedRequest,
    ProjectRoleAssignment,
    ProjectRoleRequest,
    RoleRequest,
    UserAccount,
)


def register_role_administration_routes(*, app: FastAPI, service: AuthenticationService) -> FastAPI:
    """Register system-role assignment and account-audit routes."""

    def grant_role(*, request: Request, user_id: UUID, body: RoleRequest) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            account: UserAccount = service.store.grant_role(
                user_id=user_id,
                role_name=body.role,
                actor_user_id=actor.principal.user_id,
            )
            return user_payload(account=account)
        except AccountNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except AccountConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def revoke_role(*, request: Request, user_id: UUID, role_name: str) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            account: UserAccount = service.store.revoke_role(
                user_id=user_id,
                role_name=role_name,
                actor_user_id=actor.principal.user_id,
            )
            return user_payload(account=account)
        except AccountNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except AccountConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def read_account_audit(*, request: Request) -> list[dict[str, object]]:
        require_admin(request=request)
        return [audit_payload(record=record) for record in service.store.list_audit_records()]

    def list_project_roles(
        *,
        request: Request,
        user_id: UUID,
        project: Annotated[str, Query(min_length=1)],
        includeRevoked: Annotated[bool, Query()] = False,  # noqa: N803 - wire format
    ) -> list[dict[str, object]]:
        require_admin(request=request)
        return [
            project_role_assignment_payload(assignment=assignment)
            for assignment in service.store.list_project_role_assignments(
                user_id=user_id,
                project_name=project,
                include_revoked=includeRevoked,
            )
        ]

    def grant_project_role(
        *, request: Request, user_id: UUID, body: ProjectRoleRequest
    ) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            assignment: ProjectRoleAssignment = service.store.grant_project_role(
                user_id=user_id,
                project_name=body.projectName,
                role_name=body.role,
                target_name=body.targetName,
                actor_user_id=actor.principal.user_id,
            )
            return project_role_assignment_payload(assignment=assignment)
        except AccountValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except AccountConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def revoke_project_role(*, request: Request, assignment_id: UUID) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            assignment: ProjectRoleAssignment = service.store.revoke_project_role(
                assignment_id=assignment_id,
                actor_user_id=actor.principal.user_id,
            )
            return project_role_assignment_payload(assignment=assignment)
        except AccountNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    app.post("/api/admin/users/{user_id}/roles")(grant_role)
    app.delete("/api/admin/users/{user_id}/roles/{role_name}")(revoke_role)
    app.get("/api/admin/users/{user_id}/project-roles")(list_project_roles)
    app.post("/api/admin/users/{user_id}/project-roles")(grant_project_role)
    app.delete("/api/admin/project-roles/{assignment_id}")(revoke_project_role)
    app.get("/api/admin/audit")(read_account_audit)
    return app
