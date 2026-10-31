"""Publish read-only inactive-pipeline discovery."""

from sqltide.compiler.pipeline.models import CompileAnalysis
from sqltide.executor.destruction._helpers.planning import (
    inactive_pipelines as _inactive_pipelines,
)
from sqltide.executor.destruction.models import DestructionRequest, InactivePipeline
from sqltide.executor.destruction.types import DestructionPlanningConnection


def list_inactive_pipelines(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
) -> tuple[InactivePipeline, ...]:
    """List historically owned pipelines absent from the compiled project."""

    return _inactive_pipelines(request=request, analysis=analysis, connection=connection)
