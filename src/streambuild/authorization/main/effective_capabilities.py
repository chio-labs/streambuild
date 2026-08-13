"""Public effective-capability summary entry point."""

from streambuild.auth.classes.control_store import ControlStore
from streambuild.authorization.classes.project_authorizer import ProjectAuthorizer
from streambuild.authorization.models import CapabilityRequest, EffectiveCapabilities


def effective_capabilities(
    *, store: ControlStore, request: CapabilityRequest
) -> EffectiveCapabilities:
    """Summarize one user's effective operational permissions."""

    return ProjectAuthorizer(store=store).capabilities(request=request)
