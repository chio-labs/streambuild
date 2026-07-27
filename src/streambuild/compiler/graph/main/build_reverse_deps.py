"""Build reverse dependencies for realized desired-state resources."""

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.graph._helpers.desired_state import build_desired_reverse_deps


def build_reverse_deps(desired_state: DesiredState) -> dict[ObjectKey, tuple[ObjectKey, ...]]:
    """Return downstream desired-object edges keyed by upstream object key."""

    return build_desired_reverse_deps(desired_state=desired_state)
