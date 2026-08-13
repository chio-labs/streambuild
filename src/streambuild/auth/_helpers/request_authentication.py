"""Read authenticated request-local state and enforce system administration."""

from fastapi import HTTPException, Request

from streambuild.auth.constants import ADMIN_ROLE
from streambuild.auth.models import AuthenticatedRequest


def authenticated_request(*, request: Request) -> AuthenticatedRequest:
    """Return the request authentication context or reject the request."""

    authenticated: AuthenticatedRequest | None = getattr(request.state, "authenticated", None)
    if authenticated is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return authenticated


def require_admin(*, request: Request) -> AuthenticatedRequest:
    """Require the code-defined system administrator role."""

    authenticated: AuthenticatedRequest = authenticated_request(request=request)
    if ADMIN_ROLE not in authenticated.roles:
        raise HTTPException(status_code=403, detail="System administrator role required")
    return authenticated
