"""Type-layer declarations for planner graph helpers."""

from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualTable,
)
from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
)

type DesiredObject = DesiredKafkaTable | DesiredTable | DesiredMaterializedView
type ActualObject = ActualKafkaTable | ActualTable | ActualMaterializedView
