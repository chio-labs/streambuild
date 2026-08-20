"""Apache-2.0: SQLBuild cli/commands/_helpers/compile/pipeline.py@7e3b2f854f05."""

import time
from pathlib import Path

from streambuild.compiler.access.main._compile_access_policy import compile_access_policy
from streambuild.compiler.access.models import CompiledAccessPolicy
from streambuild.compiler.compile.main._assemble_project import assemble_project
from streambuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from streambuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
    CompilerAdapterProfile,
)
from streambuild.compiler.discovery.main._discover_project_inputs import (
    discover_project_inputs,
)
from streambuild.compiler.discovery.models import DiscoveredProjectInputs, LoadedProject
from streambuild.compiler.graph.main._build_project_graph import (
    build_project_graph_from_compiled_project,
)
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.compiler.pipeline._helpers.collection_tuning import deferred_cycle_collection
from streambuild.compiler.pipeline._helpers.sensor_names import reserved_sensor_names
from streambuild.compiler.pipeline.main._realize_project import realize_project
from streambuild.compiler.pipeline.models import (
    CompilationTimings,
    CompileAnalysis,
    RealizedProject,
)
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.diagnostics.main.attach_error_diagnostic import attach_error_diagnostic
from streambuild.diagnostics.models import SourceLocation
from streambuild.diagnostics.types import DiagnosticPhase
from streambuild.sensors.main.compile_sensors import compile_sensors
from streambuild.sensors.models import CompiledSensors


def analyze_project(
    *,
    pipelines_root: Path,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> CompileAnalysis:
    """Discover, attach, compile, and graph one project without opening a connection."""

    discovery_start: int = time.monotonic_ns()
    try:
        discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
            pipelines_root=pipelines_root,
            loaded_project=loaded_project,
        )
    except Exception as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.DISCOVERY,
            code="STB-DISCOVERY-001",
            location=_project_location(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
            ),
        )
        raise
    discovery_ms: int = _elapsed_ms(discovery_start)
    compile_inputs_start: int = time.monotonic_ns()
    try:
        compile_inputs: CompileProjectInputs = build_compile_inputs(
            discovered_inputs=discovered_inputs,
            adapter_profile=adapter_profile,
        )
        access_policy: CompiledAccessPolicy | None = compile_access_policy(
            source_file=discovered_inputs.access_file,
            pipeline_names=frozenset(loaded.pipeline.name for loaded in compile_inputs.pipelines),
        )
        sensors: CompiledSensors | None = compile_sensors(
            project_dir=pipelines_root.parent,
            reserved_names=reserved_sensor_names(compile_inputs=compile_inputs),
        )
    except Exception as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.DISCOVERY,
            code="STB-DISCOVERY-001",
            location=_project_location(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
            ),
        )
        raise
    compile_inputs_ms: int = _elapsed_ms(compile_inputs_start)
    sql_analyzer: SqlModelAnalyzer = SqlModelAnalyzer(
        dialect=adapter_profile.type_inference_profile.sql_analysis_dialect
    )
    reference_rewriter: SqlReferenceRewriter = SqlReferenceRewriter(
        dialect=adapter_profile.sql_analysis_dialect
    )
    assembly_start: int = time.monotonic_ns()
    try:
        with deferred_cycle_collection():
            compiled_project: CompiledProject = assemble_project(
                inputs=compile_inputs,
                reference_rewriter=reference_rewriter,
                sql_analyzer=sql_analyzer,
            )
    except Exception as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.COMPILATION,
            code="STB-COMPILE-001",
            location=_project_location(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
            ),
        )
        raise
    assembly_ms: int = _elapsed_ms(assembly_start)
    graph_start: int = time.monotonic_ns()
    try:
        graph: ProjectGraph = build_project_graph_from_compiled_project(project=compiled_project)
    except Exception as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.GRAPH,
            code="STB-GRAPH-001",
            location=_project_location(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
            ),
        )
        raise
    graph_ms: int = _elapsed_ms(graph_start)
    realization_start: int = time.monotonic_ns()
    try:
        with deferred_cycle_collection():
            realized_project: RealizedProject = realize_project(
                project=compiled_project,
                adapter_profile=adapter_profile,
                sql_analyzer=sql_analyzer,
            )
    except Exception as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.REALIZATION,
            code="STB-REALIZATION-001",
            location=_project_location(
                pipelines_root=pipelines_root,
                loaded_project=loaded_project,
            ),
        )
        raise
    realization_ms: int = _elapsed_ms(realization_start)
    return CompileAnalysis(
        discovered_inputs=discovered_inputs,
        compile_inputs=compile_inputs,
        adapter_profile=adapter_profile,
        compiled_project=compiled_project,
        realized_project=realized_project,
        graph=graph,
        diagnostics=(),
        timings=CompilationTimings(
            discovery_ms=discovery_ms,
            compile_inputs_ms=compile_inputs_ms,
            assembly_ms=assembly_ms,
            graph_ms=graph_ms,
            realization_ms=realization_ms,
        ),
        access_policy=access_policy,
        sensors=sensors,
    )


def _elapsed_ms(start_ns: int) -> int:
    return (time.monotonic_ns() - start_ns) // 1_000_000


def _project_location(
    *, pipelines_root: Path, loaded_project: LoadedProject | None
) -> SourceLocation:
    path: Path = pipelines_root if loaded_project is None else loaded_project.source_file.file_path
    return SourceLocation(path=path, line=1, column=1)
