"""Apache-2.0: SQLBuild compiler/compile/main/_assemble_project.py@7e3b2f854f05."""

from streambuild.compiler.compile._helpers.audit_validation import validated_sql_audits
from streambuild.compiler.compile._helpers.naming import validate_compiled_project_relation_names
from streambuild.compiler.compile._helpers.replay_policies import (
    resolve_source_replay_lineage_mode,
)
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledProject,
    CompiledSource,
    CompileProjectInputs,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.testing.main._build_sql_test_cases import build_sql_test_cases
from streambuild.compiler.testing.models import SqlTestCase


def assemble_project(
    *,
    inputs: CompileProjectInputs,
    reference_rewriter: SqlReferenceRewriter,
    sql_analyzer: SqlModelAnalyzer,
) -> CompiledProject:
    """Compile and validate every attached project resource exactly once."""

    pipelines: tuple[CompiledPipeline, ...] = tuple(
        compile_pipeline(loaded_pipeline=loaded_pipeline, sql_analyzer=sql_analyzer)
        for loaded_pipeline in inputs.pipelines
    )
    sources_by_name: dict[str, CompiledSource] = {
        source.name: CompiledSource(
            key=LogicalResourceKey(
                resource_type=LogicalResourceType.SOURCE,
                name=source.name,
            ),
            source=source,
            effective_replay_lineage_mode=resolve_source_replay_lineage_mode(source=source),
        )
        for source in inputs.sources
    }
    models: list[CompiledModel] = []
    pipeline: CompiledPipeline
    for pipeline in pipelines:
        if pipeline.source is not None:
            sources_by_name.setdefault(pipeline.source.key.name, pipeline.source)
        models.extend(pipeline.models)
    test_cases: tuple[SqlTestCase, ...] = build_sql_test_cases(
        loaded_tests=inputs.tests,
        compiled_pipelines=pipelines,
        reference_rewriter=reference_rewriter,
        comparison_renderer=inputs.adapter_profile.render_set_difference_comparison,
        dialect=inputs.adapter_profile.sql_analysis_dialect,
    )
    project: CompiledProject = CompiledProject(
        sources=tuple(sources_by_name.values()),
        models=tuple(models),
        pipelines=pipelines,
        tests=inputs.tests,
        test_cases=test_cases,
        audits=validated_sql_audits(
            loaded_audits=inputs.audits,
            compiled_pipelines=pipelines,
        ),
        macro_registry=inputs.macro_registry,
        macro_context=inputs.macro_context,
    )
    validate_compiled_project_relation_names(project=project)
    return project
