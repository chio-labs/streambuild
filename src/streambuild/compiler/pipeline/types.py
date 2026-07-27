"""Project-realization type contracts."""

from streambuild.adapter.models import AdapterManagedSource, AdapterMaterializedView, AdapterTable
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
)

type AdapterResource = AdapterManagedSource | AdapterTable | AdapterMaterializedView
type DesiredObject = DesiredKafkaTable | DesiredTable | DesiredMaterializedView
