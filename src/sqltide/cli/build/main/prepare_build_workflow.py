"""Publish connected workflow preparation to mode-aware callers."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.cli.build._helpers.workflow_preparation import (
    prepare_build_workflow as _prepare_build_workflow,
)
from sqltide.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
    WorkflowPreparationOptions,
)
from sqltide.compiler.compile.models import CompilerAdapterProfile
from sqltide.compiler.pipeline.models import CompileAnalysis


def prepare_build_workflow(
    *,
    analysis: CompileAnalysis,
    options: WorkflowPreparationOptions,
    client: AdapterConnection,
    adapter_profile: CompilerAdapterProfile,
) -> DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation:
    """Return one complete workflow assembled from fresh connected inspection."""

    return _prepare_build_workflow(
        analysis=analysis,
        options=options,
        client=client,
        adapter_profile=adapter_profile,
    )
