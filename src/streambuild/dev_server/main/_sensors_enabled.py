"""Resolve target sensor automation enablement."""

from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.models import CompileAnalysis


def sensors_enabled(analysis: CompileAnalysis) -> bool:
    """Return whether the compiled target enables the sensor dispatcher."""

    loaded_project: LoadedProject | None = analysis.discovered_inputs.loaded_project
    return bool(
        loaded_project is not None
        and loaded_project.effective_configuration is not None
        and loaded_project.effective_configuration.sensors.enabled
    )
