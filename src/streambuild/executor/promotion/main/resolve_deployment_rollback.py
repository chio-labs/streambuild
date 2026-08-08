"""Resolve a whole-deployment rollback from publication history and live bindings."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.promotion._helpers.rollback import resolve_rollback_plan
from streambuild.executor.promotion.models import RollbackPlan, RollbackRequest


def resolve_deployment_rollback(
    *, request: RollbackRequest, client: AdapterConnection
) -> RollbackPlan:
    """Resolve the active publication and requested retained rollback target."""

    return resolve_rollback_plan(request=request, client=client)
