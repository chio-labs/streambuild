"""Order object keys so dependencies precede dependents."""

from __future__ import annotations

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.main.build_reverse_deps import build_reverse_deps
from streambuild.compiler.planner.types import DesiredObject
from streambuild.compiler.shared.models import (
    ObjectKey,
)


def topologically_order_keys(
    *, desired_state: DesiredState, included_keys: set[ObjectKey]
) -> tuple[ObjectKey, ...]:
    """Return included desired-object keys in stable dependency order."""

    desired_index_by_key: dict[ObjectKey, int] = {
        object_.key: index for index, object_ in enumerate(desired_state.objects)
    }
    object_by_key: dict[ObjectKey, DesiredObject] = {
        object_.key: object_ for object_ in desired_state.objects if object_.key in included_keys
    }
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_reverse_deps(desired_state)
    indegree_by_key: dict[ObjectKey, int] = {key: 0 for key in object_by_key}
    key: ObjectKey
    object_: DesiredObject
    for key, object_ in object_by_key.items():
        indegree_by_key[key] = sum(1 for dep_key in object_.deps if dep_key in included_keys)

    ready_keys: list[ObjectKey] = sorted(
        (key for key, indegree in indegree_by_key.items() if indegree == 0),
        key=lambda key: desired_index_by_key[key],
    )
    ordered_keys: list[ObjectKey] = []

    while ready_keys:
        current_key: ObjectKey = ready_keys.pop(0)
        ordered_keys.append(current_key)
        downstream_key: ObjectKey
        for downstream_key in reverse_deps.get(current_key, ()):
            if downstream_key not in indegree_by_key:
                continue
            indegree_by_key[downstream_key] -= 1
            if indegree_by_key[downstream_key] == 0:
                ready_keys.append(downstream_key)
                ready_keys.sort(key=lambda key: desired_index_by_key[key])

    return tuple(ordered_keys)
