"""Public operational authorization entry point."""

from sqltide.auth.classes.control_store import ControlStore
from sqltide.authorization.classes.project_authorizer import ProjectAuthorizer
from sqltide.authorization.models import AuthorizationDecision, AuthorizationRequest


def authorize_operation(
    *, store: ControlStore, request: AuthorizationRequest
) -> AuthorizationDecision:
    """Evaluate one authoritative operation against current membership."""

    return ProjectAuthorizer(store=store).decide(request=request)
