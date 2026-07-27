"""Public logical-project realization entry point."""

from streambuild.compiler.compile.models import CompiledProject, CompilerAdapterProfile
from streambuild.compiler.pipeline._helpers.realization import build_realized_project
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer


def realize_project(
    *,
    project: CompiledProject,
    adapter_profile: CompilerAdapterProfile,
    sql_analyzer: SqlModelAnalyzer,
) -> RealizedProject:
    """Realize a complete logical project through connection-free adapter callbacks."""

    return build_realized_project(
        project=project,
        adapter_profile=adapter_profile,
        sql_analyzer=sql_analyzer,
    )
