"""Publish canonical project manifest construction."""

from streambuild.adapter.models import AdapterManifest
from streambuild.compiler.manifest._helpers.build import build_manifest_record
from streambuild.compiler.pipeline.models import CompileAnalysis


def build_manifest(
    *,
    analysis: CompileAnalysis,
    invocation_id: str,
    project_identity: str,
    target_database: str,
    tool_version: str,
    project_revision: str | None = None,
    published_at: str | None = None,
) -> AdapterManifest:
    """Return one complete, deterministically fingerprinted project manifest."""

    return build_manifest_record(
        analysis=analysis,
        invocation_id=invocation_id,
        project_identity=project_identity,
        target_database=target_database,
        tool_version=tool_version,
        project_revision=project_revision,
        published_at=published_at,
    )
