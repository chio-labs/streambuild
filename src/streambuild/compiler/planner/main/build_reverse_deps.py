"""Build the reverse dependency map for a desired state."""

from __future__ import annotations

from streambuild.compiler.compile.models import DesiredState, ObjectKey
from streambuild.compiler.planner.types import DesiredObject


def build_reverse_deps(desired_state: DesiredState) -> dict[ObjectKey, tuple[ObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    reverse_deps: dict[ObjectKey, list[ObjectKey]] = {}
    object_: DesiredObject
    for object_ in desired_state.objects:
        dep_key: ObjectKey
        for dep_key in object_.deps:
            reverse_deps.setdefault(dep_key, []).append(object_.key)

    return {
        dep_key: tuple(sorted(keys, key=lambda key: (key.object_type, key.name)))
        for dep_key, keys in reverse_deps.items()
    }
