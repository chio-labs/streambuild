"""Register authentication configuration, session, login, and logout routes."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from streambuild.auth._helpers.authentication_payloads import (
    account_principal,
    authenticated_payload,
    authentication_config_payload,
)
from streambuild.auth._helpers.request_authentication import authenticated_request
from streambuild.auth._helpers.usernames import canonical_username
from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.classes.login_attempt_limiter import LoginAttemptLimiter
from streambuild.auth.exceptions import AccountValidationError
from streambuild.auth.models import (
    AuthenticatedRequest,
    LoginRequest,
    SessionCredentials,
    UserAccount,
)
from streambuild.auth.types import AuthenticationMode, AuthenticationSource


def register_session_routes(
    *, app: FastAPI, service: AuthenticationService, limiter: LoginAttemptLimiter
) -> FastAPI:
    """Register browser authentication lifecycle routes."""

    def read_auth_config() -> dict[str, object]:
        return authentication_config_payload(settings=service.settings)

    def read_current_user(*, request: Request) -> dict[str, object]:
        return authenticated_payload(
            authenticated=authenticated_request(request=request),
            mode=service.settings.mode,
        )

    def login(*, request: Request, body: LoginRequest) -> Response:
        if service.settings.mode != AuthenticationMode.PASSWORD:
            raise HTTPException(status_code=404, detail="Password login is not enabled")
        client_host: str = request.client.host if request.client else "unknown"
        try:
            limiter_username: str = canonical_username(body.username)
        except AccountValidationError:
            limiter_username = "<invalid>"
        ip_key: str = f"ip:{client_host}"
        user_key: str = f"user:{limiter_username}"
        limiter.check(ip_key=ip_key, user_key=user_key)
        result: tuple[UserAccount, SessionCredentials] | None = service.store.authenticate_password(
            username=body.username,
            password=body.password,
            session_ttl_seconds=service.settings.session_ttl_seconds,
        )
        if result is None:
            limiter.failed(ip_key=ip_key, user_key=user_key)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        limiter.succeeded(user_key=user_key)
        account, credentials = result
        authenticated: AuthenticatedRequest = AuthenticatedRequest(
            principal=account_principal(account=account, source=AuthenticationSource.PASSWORD),
            roles=account.roles,
            csrf_token=credentials.csrf_token,
        )
        response: JSONResponse = JSONResponse(
            content=authenticated_payload(authenticated=authenticated, mode=service.settings.mode)
        )
        response.set_cookie(
            key=service.settings.session_cookie_name,
            value=credentials.token,
            httponly=True,
            secure=service.settings.session_cookie_secure,
            samesite="lax",
            max_age=service.settings.session_ttl_seconds,
            path="/",
        )
        return response

    def logout(*, request: Request) -> Response:
        authenticated: AuthenticatedRequest = authenticated_request(request=request)
        token: str | None = request.cookies.get(service.settings.session_cookie_name)
        if token is not None:
            service.store.revoke_session(
                token=token,
                actor_user_id=authenticated.principal.user_id,
            )
        response: JSONResponse = JSONResponse(content={"status": "ok"})
        response.delete_cookie(service.settings.session_cookie_name, path="/")
        return response

    app.get("/api/auth/config")(read_auth_config)
    app.get("/api/auth/me")(read_current_user)
    app.post("/api/auth/login")(login)
    app.post("/api/auth/logout")(logout)
    return app
