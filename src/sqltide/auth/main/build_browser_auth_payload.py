"""Build the authenticated browser bootstrap payload."""

from fastapi import Request

from sqltide.auth._helpers.authentication_payloads import (
    authenticated_payload,
    authentication_config_payload,
)
from sqltide.auth.classes.authentication_service import AuthenticationService
from sqltide.auth.main.read_authenticated_request import read_authenticated_request


def build_browser_auth_payload(
    *, service: AuthenticationService, request: Request
) -> dict[str, object]:
    """Return authentication configuration and the current authenticated session."""

    return {
        "config": authentication_config_payload(settings=service.settings),
        "session": authenticated_payload(
            authenticated=read_authenticated_request(request=request),
            mode=service.settings.mode,
        ),
    }
