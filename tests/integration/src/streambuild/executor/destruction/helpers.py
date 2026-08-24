from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.pipeline.models import CompileAnalysis


def realized_relation_names(
    *, analysis: CompileAnalysis, logical_keys: tuple[LogicalResourceKey, ...]
) -> frozenset[str]:
    relation_names: set[str] = set()
    for logical_key in logical_keys:
        resources: tuple[
            AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView,
            ...,
        ] = analysis.realized_project.resources_by_logical_key[logical_key]
        relation_names.update(resource.name for resource in resources)
    return frozenset(relation_names)
