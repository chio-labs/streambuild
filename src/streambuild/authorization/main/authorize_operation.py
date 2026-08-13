"""Public operational authorization entry point."""

from streambuild.auth.classes.control_store import ControlStore
from streambuild.authorization.classes.project_authorizer import ProjectAuthorizer
from streambuild.authorization.models import AuthorizationDecision, AuthorizationRequest


def authorize_operation(
    *, store: ControlStore, request: AuthorizationRequest
) -> AuthorizationDecision:
    """Evaluate one authoritative operation against current membership."""

    return ProjectAuthorizer(store=store).decide(request=request)
