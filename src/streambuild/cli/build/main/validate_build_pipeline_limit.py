"""Absolute build-scope validation resolved from committed project configuration."""

from streambuild.cli.build.exceptions import BuildPipelineLimitError
from streambuild.cli.selection.main._selection import resolve_selection
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.discovery.models import EffectiveProjectConfiguration, LoadedProject
from streambuild.compiler.pipeline.models import CompileAnalysis


def validate_build_pipeline_limit(*, analysis: CompileAnalysis, selectors: tuple[str, ...]) -> None:
    """Reject a build whose final execution closure spans too many pipelines."""

    loaded_project: LoadedProject | None = analysis.discovered_inputs.loaded_project
    effective: EffectiveProjectConfiguration | None = (
        None if loaded_project is None else loaded_project.effective_configuration
    )
    if effective is None or effective.build.max_pipelines is None:
        return
    max_pipelines: int = effective.build.max_pipelines
    execution_keys: frozenset[LogicalResourceKey] = resolve_selection(
        realized_project=analysis.realized_project,
        graph=analysis.graph,
        selectors=selectors,
    ).execution_logical_model_keys
    pipeline_names: tuple[str, ...] = tuple(
        sorted(
            {
                model.pipeline_name
                for model in analysis.compiled_project.models
                if model.key in execution_keys
            }
        )
    )
    if len(pipeline_names) <= max_pipelines:
        return
    raise BuildPipelineLimitError(
        f"Build affects {len(pipeline_names)} pipelines, exceeding max_pipelines={max_pipelines} "
        f"for target '{effective.target_name}': {', '.join(pipeline_names)}"
    )
