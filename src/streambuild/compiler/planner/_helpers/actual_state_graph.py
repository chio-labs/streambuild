"""Build project-level actual-state graphs from normalized objects."""

from streambuild.compiler.planner.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
    ActualView,
)


def build_actual_state(
    objects: tuple[ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView, ...],
) -> ActualState:
    """Build a deterministically ordered actual-state graph."""

    sorted_objects: tuple[
        ActualKafkaTable | ActualTable | ActualMaterializedView | ActualView, ...
    ] = tuple(sorted(objects, key=lambda object_: (object_.key.object_type, object_.key.name)))
    return ActualState(objects=sorted_objects)
