"""Publish stable manifest project identity resolution."""

from streambuild.compiler.pipeline.models import CompileAnalysis


def resolve_manifest_project_identity(*, analysis: CompileAnalysis) -> str:
    """Prefer the declared project name and fall back to the project directory name."""

    return analysis.compiled_project.project_name or analysis.discovered_inputs.project_dir.name
