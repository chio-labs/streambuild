"""Apache-2.0: SQLBuild compiler/compile/main/_assemble_project.py@7e3b2f854f05."""

from streambuild.compiler.compile._helpers.audit_validation import validated_sql_audits
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledProject,
    CompiledSource,
    CompileProjectInputs,
)
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
    sources_by_name: dict[str, CompiledSource] = {}
    models: list[CompiledModel] = []
    pipeline: CompiledPipeline
    for pipeline in pipelines:
        sources_by_name.setdefault(pipeline.source.key.name, pipeline.source)
        models.extend(pipeline.models)
    test_cases: tuple[SqlTestCase, ...] = build_sql_test_cases(
        loaded_tests=inputs.tests,
        compiled_pipelines=pipelines,
        reference_rewriter=reference_rewriter,
        comparison_renderer=inputs.adapter_profile.render_set_difference_comparison,
        dialect=inputs.adapter_profile.sql_analysis_dialect,
    )
    return CompiledProject(
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
