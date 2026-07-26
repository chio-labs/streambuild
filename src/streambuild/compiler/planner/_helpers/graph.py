"""Graph traversal helpers for planning over desired state."""

from __future__ import annotations

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.main.build_reverse_deps import build_reverse_deps
from streambuild.compiler.planner.main.topologically_order_keys import topologically_order_keys
from streambuild.compiler.planner.types import DesiredObject
from streambuild.compiler.shared.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.shared.models import (
    DesiredMaterializedView,
    ObjectKey,
)


def descendant_keys(*, desired_state: DesiredState, root_key: ObjectKey) -> tuple[ObjectKey, ...]:
    """Return the transitive downstream object keys rooted at `root_key`."""

    object_by_key: dict[ObjectKey, DesiredObject] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_reverse_deps(desired_state)
    visited: set[ObjectKey] = set()
    stack: list[ObjectKey] = [root_key]

    while stack:
        current_key: ObjectKey = stack.pop()
        if current_key in visited or current_key not in object_by_key:
            continue

        visited.add(current_key)
        downstream_keys: tuple[ObjectKey, ...] = reverse_deps.get(current_key, ())
        stack.extend(reversed(downstream_keys))

    return topologically_order_keys(desired_state=desired_state, included_keys=visited)


def nearest_upstream_replay_anchor_key(
    *,
    desired_state: DesiredState,
    root_key: ObjectKey,
    allow_root_key: bool = True,
) -> ObjectKey:
    """Return the nearest eligible upstream replay-anchor table for rebuild planning."""

    object_by_key: dict[ObjectKey, DesiredObject] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    current_key: ObjectKey = root_key

    while True:
        current_object: DesiredObject | None = object_by_key.get(current_key)
        if current_object is None:
            return current_key

        if isinstance(current_object, DesiredMaterializedView):
            current_key = build_table_key(current_object.source_table_name)
            continue

        if current_key in desired_state.replay_anchor_keys and (
            allow_root_key or current_key != root_key
        ):
            return current_key

        table_dep_keys: tuple[ObjectKey, ...] = tuple(
            dep_key
            for dep_key in current_object.deps
            if dep_key.object_type == DESIRED_OBJECT_TYPE_TABLE
        )
        if not table_dep_keys:
            return current_key

        current_key = table_dep_keys[0]


def build_table_key(name: str) -> ObjectKey:
    """Build a table object key using the current desired-state table identity."""

    return ObjectKey(database=None, object_type=DESIRED_OBJECT_TYPE_TABLE, name=name)
