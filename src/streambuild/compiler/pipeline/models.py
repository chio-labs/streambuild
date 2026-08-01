"""Immutable results for the project compilation lifecycle."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
    CompilerAdapterProfile,
    DesiredState,
    LogicalResourceKey,
)
from streambuild.compiler.discovery.models import DiscoveredProjectInputs
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.diagnostics.models import CompilerDiagnostic


@dataclass(frozen=True)
class CompilationTimings:
    """Elapsed milliseconds for each named project compilation phase."""

    discovery_ms: int
    compile_inputs_ms: int
    assembly_ms: int
    graph_ms: int
    realization_ms: int


@dataclass(frozen=True)
class RealizedProject:
    """Adapter resources mapped back to their sole logical project aggregate."""

    project: CompiledProject
    resources_by_logical_key: Mapping[
        LogicalResourceKey,
        tuple[AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView, ...],
    ]
    relation_name_by_logical_key: Mapping[LogicalResourceKey, str]
    resolved_query_by_model_key: Mapping[LogicalResourceKey, str]
    desired_state: DesiredState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resources_by_logical_key",
            MappingProxyType(dict(self.resources_by_logical_key)),
        )
        object.__setattr__(
            self,
            "relation_name_by_logical_key",
            MappingProxyType(dict(self.relation_name_by_logical_key)),
        )
        object.__setattr__(
            self,
            "resolved_query_by_model_key",
            MappingProxyType(dict(self.resolved_query_by_model_key)),
        )


@dataclass(frozen=True)
class CompileAnalysis:
    """Command-neutral output shared by every compile consumer."""

    discovered_inputs: DiscoveredProjectInputs
    compile_inputs: CompileProjectInputs
    adapter_profile: CompilerAdapterProfile
    compiled_project: CompiledProject
    realized_project: RealizedProject
    graph: ProjectGraph
    diagnostics: tuple[CompilerDiagnostic, ...]
    timings: CompilationTimings
