"""Compose authentication middleware and HTTP routes."""

from fastapi import FastAPI

from sqltide.auth._helpers.account_administration_routes import (
    register_account_administration_routes,
)
from sqltide.auth._helpers.authentication_middleware import (
    register_authentication_middleware,
)
from sqltide.auth._helpers.role_administration_routes import (
    register_role_administration_routes,
)
from sqltide.auth._helpers.session_routes import register_session_routes
from sqltide.auth.classes.authentication_service import AuthenticationService
from sqltide.auth.classes.login_attempt_limiter import LoginAttemptLimiter


def register_authentication_routes(*, app: FastAPI, service: AuthenticationService) -> FastAPI:
    """Register auth/account routes and global API authentication."""

    limiter: LoginAttemptLimiter = LoginAttemptLimiter()
    _ = register_authentication_middleware(app=app, service=service)
    _ = register_session_routes(app=app, service=service, limiter=limiter)
    _ = register_account_administration_routes(app=app, service=service)
    return register_role_administration_routes(app=app, service=service)
