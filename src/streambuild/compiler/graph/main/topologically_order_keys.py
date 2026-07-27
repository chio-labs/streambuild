"""Order realized desired-state resources by dependency."""

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.graph._helpers.desired_state import order_desired_keys


def topologically_order_keys(
    *, desired_state: DesiredState, included_keys: set[ObjectKey]
) -> tuple[ObjectKey, ...]:
    """Return included desired-object keys in stable dependency order."""

    return order_desired_keys(desired_state=desired_state, included_keys=included_keys)
