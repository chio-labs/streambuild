"""Install global API authentication and mutation request proof checks."""

from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from streambuild.auth.classes.authentication_service import AuthenticationService
from streambuild.auth.constants import CSRF_HEADER, PUBLIC_API_PATHS, UNSAFE_HTTP_METHODS
from streambuild.auth.exceptions import (
    AccountConflictError,
    AuthenticationError,
    AuthorizationError,
)
from streambuild.auth.models import AuthenticatedRequest


def register_authentication_middleware(*, app: FastAPI, service: AuthenticationService) -> FastAPI:
    """Require one authenticated principal for every private API request."""

    async def authenticate_request(*arguments: object) -> Response:
        request: Request = cast(Request, arguments[0])
        call_next: RequestResponseEndpoint = cast(RequestResponseEndpoint, arguments[1])
        if not request.url.path.startswith("/api/") or request.url.path in PUBLIC_API_PATHS:
            return await call_next(request)
        try:
            authenticated: AuthenticatedRequest = service.authenticate(
                headers=request.headers,
                cookies=request.cookies,
            )
            if request.method in UNSAFE_HTTP_METHODS:
                service.require_csrf(
                    authenticated=authenticated,
                    supplied_token=request.headers.get(CSRF_HEADER),
                )
            request.state.authenticated = authenticated
            return await call_next(request)
        except AuthenticationError as error:
            return JSONResponse(
                status_code=401,
                content={"detail": str(error)},
                headers={"WWW-Authenticate": "Session"},
            )
        except (AuthorizationError, AccountConflictError) as error:
            return JSONResponse(status_code=403, content={"detail": str(error)})

    app.middleware("http")(authenticate_request)
    return app
