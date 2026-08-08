"""Publish connected workflow preparation to mode-aware CLI commands."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.workflow_preparation import (
    prepare_build_workflow as _prepare_build_workflow,
)
from streambuild.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
    WorkflowPreparationOptions,
)
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.pipeline.models import CompileAnalysis


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
