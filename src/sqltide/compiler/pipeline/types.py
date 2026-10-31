"""Project-realization type contracts."""

from sqltide.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from sqltide.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    DesiredView,
)

type AdapterResource = AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView
type DesiredObject = DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
