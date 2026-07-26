"""Primary planner entrypoints."""

from streambuild.adapter.types import AdapterResourceRenderer
from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.planner._helpers.deployment import build_deployment_plan
from streambuild.compiler.planner.models import ActualState, DeploymentPlan


def plan_deployment(
    *,
    desired_state: DesiredState,
    actual_state: ActualState,
    default_database: str,
    render_resource: AdapterResourceRenderer,
    deployment_id: str | None = None,
    full_refresh_keys: frozenset[ObjectKey] = frozenset(),
    start_time_keys: frozenset[ObjectKey] = frozenset(),
    start_time: str | None = None,
) -> DeploymentPlan:
    """Build a conservative staged deployment plan from desired and actual state."""

    return build_deployment_plan(
        desired_state=desired_state,
        actual_state=actual_state,
        default_database=default_database,
        render_resource=render_resource,
        deployment_id=deployment_id,
        full_refresh_keys=full_refresh_keys,
        start_time_keys=start_time_keys,
        start_time=start_time,
    )
