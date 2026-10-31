"""Public authenticated-request accessor."""

from fastapi import Request

from sqltide.auth._helpers.request_authentication import authenticated_request
from sqltide.auth.models import AuthenticatedRequest


def read_authenticated_request(*, request: Request) -> AuthenticatedRequest:
    """Return middleware-authenticated request state or reject the request."""

    return authenticated_request(request=request)
