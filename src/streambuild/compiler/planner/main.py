"""Primary planner entrypoints."""

from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner._helpers.deployment import build_deployment_plan
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.models import ObjectKey


def plan_deployment(
    *,
    desired_state: DesiredState,
    actual_state: ActualState,
    default_database: str,
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
        deployment_id=deployment_id,
        full_refresh_keys=full_refresh_keys,
        start_time_keys=start_time_keys,
        start_time=start_time,
    )
