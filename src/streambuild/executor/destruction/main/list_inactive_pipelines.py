"""Publish read-only inactive-pipeline discovery."""

from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.destruction._helpers.planning import (
    inactive_pipelines as _inactive_pipelines,
)
from streambuild.executor.destruction.models import DestructionRequest, InactivePipeline
from streambuild.executor.destruction.types import DestructionPlanningConnection


def list_inactive_pipelines(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
) -> tuple[InactivePipeline, ...]:
    """List historically owned pipelines absent from the compiled project."""

    return _inactive_pipelines(request=request, analysis=analysis, connection=connection)
