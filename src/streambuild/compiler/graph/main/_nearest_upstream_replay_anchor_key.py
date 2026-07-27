"""Find the nearest upstream replay anchor in realized desired state."""

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.graph._helpers.desired_state import find_nearest_replay_anchor_key


def nearest_upstream_replay_anchor_key(
    *,
    desired_state: DesiredState,
    root_key: ObjectKey,
    allow_root_key: bool = True,
) -> ObjectKey:
    """Return the nearest eligible upstream replay-anchor table for rebuild planning."""

    return find_nearest_replay_anchor_key(
        desired_state=desired_state,
        root_key=root_key,
        allow_root_key=allow_root_key,
    )
