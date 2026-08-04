"""Publish direct build preview preparation to external callers."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build._helpers.preview import (
    build_direct_build_preview as _build_direct_build_preview,
)
from streambuild.cli.build.models import DirectBuildPreviewContext, WorkflowPreparationOptions
from streambuild.compiler.pipeline.models import CompileAnalysis


def build_direct_build_preview(
    *,
    options: WorkflowPreparationOptions,
    client: AdapterConnection,
    analysis: CompileAnalysis,
    effective_start_time: str | None = None,
) -> DirectBuildPreviewContext:
    """Plan one selected direct closure through the canonical connected preview path."""

    return _build_direct_build_preview(
        options=options,
        client=client,
        analysis=analysis,
        effective_start_time=effective_start_time,
    )
