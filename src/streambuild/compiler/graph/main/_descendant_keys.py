"""Collect descendants of one realized desired-state resource."""

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.graph._helpers.desired_state import collect_desired_descendant_keys


def descendant_keys(*, desired_state: DesiredState, root_key: ObjectKey) -> tuple[ObjectKey, ...]:
    """Return the transitive downstream object keys rooted at `root_key`."""

    return collect_desired_descendant_keys(desired_state=desired_state, root_key=root_key)
