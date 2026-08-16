"""Register account administration routes."""

from uuid import UUID

from fastapi import FastAPI, HTTPException, Request

from streambuild.auth._helpers.authentication_payloads import user_payload
from streambuild.auth._helpers.request_authentication import require_admin
from streambuild.auth._helpers.usernames import canonical_username
from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.exceptions import (
    AccountConflictError,
    AccountNotFoundError,
    AccountValidationError,
    PasswordValidationError,
)
from streambuild.auth.models import (
    AuthenticatedRequest,
    CreateUserRequest,
    PasswordResetRequest,
    UpdateUserRequest,
    UserAccount,
)
from streambuild.auth.types import AuthenticationSource

_DISPLAY_NAME_FIELD: str = "displayName"
_EMAIL_FIELD: str = "email"


def register_account_administration_routes(
    *, app: FastAPI, service: AuthenticationService
) -> FastAPI:
    """Register account list, creation, update, and password-reset routes."""

    def list_users(*, request: Request) -> list[dict[str, object]]:
        require_admin(request=request)
        return [user_payload(account=account) for account in service.store.list_users()]

    def create_user(*, request: Request, body: CreateUserRequest) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        source: AuthenticationSource = AuthenticationSource(body.authenticationSource)
        if source == AuthenticationSource.PASSWORD and body.password is None:
            raise HTTPException(status_code=400, detail="Password account requires a password")
        if source == AuthenticationSource.TRUSTED_PROXY and body.password is not None:
            raise HTTPException(status_code=400, detail="Proxy account must not include a password")
        try:
            account: UserAccount = service.store.create_user(
                username=body.username,
                display_name=body.displayName,
                email=body.email,
                password=body.password,
                authentication_source=(
                    source if source == AuthenticationSource.TRUSTED_PROXY else None
                ),
                external_subject=(
                    canonical_username(body.username)
                    if source == AuthenticationSource.TRUSTED_PROXY
                    else None
                ),
                roles=tuple(body.roles),
                actor_user_id=actor.principal.user_id,
            )
            return user_payload(account=account)
        except PasswordValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (AccountConflictError, AccountNotFoundError, AccountValidationError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def update_user(
        *, request: Request, user_id: UUID, body: UpdateUserRequest
    ) -> dict[str, object]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            account: UserAccount | None = service.store.get_user_by_id(user_id=user_id)
            if account is None:
                raise AccountNotFoundError(f"User '{user_id}' was not found")
            profile_fields: set[str] = body.model_fields_set
            account = service.store.update_account(
                user_id=user_id,
                display_name=(
                    body.displayName
                    if _DISPLAY_NAME_FIELD in profile_fields
                    else account.display_name
                ),
                email=body.email if _EMAIL_FIELD in profile_fields else account.email,
                is_active=body.active if body.active is not None else account.is_active,
                actor_user_id=actor.principal.user_id,
            )
            return user_payload(account=account)
        except AccountNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except AccountConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def reset_password(
        *, request: Request, user_id: UUID, body: PasswordResetRequest
    ) -> dict[str, str]:
        actor: AuthenticatedRequest = require_admin(request=request)
        try:
            service.store.reset_password(
                user_id=user_id,
                password=body.password,
                actor_user_id=actor.principal.user_id,
            )
        except AccountNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PasswordValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "ok"}

    app.get("/api/admin/users")(list_users)
    app.post("/api/admin/users")(create_user)
    app.patch("/api/admin/users/{user_id}")(update_user)
    app.post("/api/admin/users/{user_id}/password")(reset_password)
    return app
