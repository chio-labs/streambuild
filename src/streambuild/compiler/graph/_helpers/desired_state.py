"""Pure traversal algorithms over realized desired-state resources."""

from streambuild.compiler.compile.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
    ObjectKey,
)
from streambuild.compiler.graph.exceptions import GraphInputError


def build_desired_reverse_deps(
    *, desired_state: DesiredState
) -> dict[ObjectKey, tuple[ObjectKey, ...]]:
    """Build downstream desired-object keys by upstream key."""

    reverse_deps: dict[ObjectKey, list[ObjectKey]] = {}
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for object_ in desired_state.objects:
        dep_key: ObjectKey
        for dep_key in object_.deps:
            reverse_deps.setdefault(dep_key, []).append(object_.key)
    return {
        dep_key: tuple(sorted(keys, key=_object_key_sort_key))
        for dep_key, keys in reverse_deps.items()
    }


def order_desired_keys(
    *, desired_state: DesiredState, included_keys: set[ObjectKey]
) -> tuple[ObjectKey, ...]:
    """Order included desired-object keys stably or reject a cycle."""

    desired_index_by_key: dict[ObjectKey, int] = {
        object_.key: index for index, object_ in enumerate(desired_state.objects)
    }
    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ] = {object_.key: object_ for object_ in desired_state.objects if object_.key in included_keys}
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_desired_reverse_deps(
        desired_state=desired_state
    )
    indegree_by_key: dict[ObjectKey, int] = {}
    key: ObjectKey
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for key, object_ in object_by_key.items():
        indegree_by_key[key] = sum(1 for dep_key in object_.deps if dep_key in object_by_key)
    ready_keys: list[ObjectKey] = sorted(
        (key for key, indegree in indegree_by_key.items() if indegree == 0),
        key=desired_index_by_key.__getitem__,
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
                ready_keys.sort(key=desired_index_by_key.__getitem__)
    if len(ordered_keys) != len(indegree_by_key):
        unresolved_keys: tuple[ObjectKey, ...] = tuple(
            key for key in object_by_key if key not in ordered_keys
        )
        unresolved_names: str = ", ".join(
            f"{key.object_type}:{key.name}" for key in unresolved_keys
        )
        raise GraphInputError(f"Dependency cycle detected involving: {unresolved_names}")
    return tuple(ordered_keys)


def collect_desired_descendant_keys(
    *, desired_state: DesiredState, root_key: ObjectKey
) -> tuple[ObjectKey, ...]:
    """Collect one desired-object downstream closure in dependency order."""

    object_keys: set[ObjectKey] = {object_.key for object_ in desired_state.objects}
    reverse_deps: dict[ObjectKey, tuple[ObjectKey, ...]] = build_desired_reverse_deps(
        desired_state=desired_state
    )
    visited_keys: set[ObjectKey] = set()
    stack: list[ObjectKey] = [root_key]
    while stack:
        current_key: ObjectKey = stack.pop()
        if current_key in visited_keys or current_key not in object_keys:
            continue
        visited_keys.add(current_key)
        stack.extend(reversed(reverse_deps.get(current_key, ())))
    return order_desired_keys(desired_state=desired_state, included_keys=visited_keys)


def find_nearest_replay_anchor_key(
    *,
    desired_state: DesiredState,
    root_key: ObjectKey,
    allow_root_key: bool,
) -> ObjectKey:
    """Find the nearest eligible table through realized driving dependencies only."""

    object_by_key: dict[
        ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    ] = {object_.key: object_ for object_ in desired_state.objects}
    current_key: ObjectKey = root_key
    visited_keys: set[ObjectKey] = set()
    while current_key not in visited_keys:
        visited_keys.add(current_key)
        current_object: (
            DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView | None
        ) = object_by_key.get(current_key)
        if current_object is None:
            return current_key
        if isinstance(current_object, DesiredMaterializedView):
            current_key = _table_key(current_object.source_table_name)
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
    raise GraphInputError(
        f"Dependency cycle detected while finding replay anchor for '{root_key.name}'"
    )


def _table_key(name: str) -> ObjectKey:
    return ObjectKey(database=None, object_type=DESIRED_OBJECT_TYPE_TABLE, name=name)


def _object_key_sort_key(key: ObjectKey) -> tuple[str, str]:
    return (key.object_type, key.name)
