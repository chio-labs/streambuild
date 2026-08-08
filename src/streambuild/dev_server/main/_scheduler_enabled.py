"""Resolve target audit scheduler enablement."""

from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.models import CompileAnalysis


def scheduler_enabled(analysis: CompileAnalysis) -> bool:
    """Return whether the compiled target enables scheduled audits."""

    loaded_project: LoadedProject | None = analysis.discovered_inputs.loaded_project
    return bool(
        loaded_project is not None
        and loaded_project.effective_configuration is not None
        and loaded_project.effective_configuration.audit_scheduler.enabled
    )
