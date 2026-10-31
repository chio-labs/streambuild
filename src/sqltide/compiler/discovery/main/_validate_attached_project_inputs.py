"""Validate one complete set of attached project inputs."""

from sqltide.compiler.audit_discovery.models import LoadedSqlAudit
from sqltide.compiler.discovery._helpers.validation import (
    validate_discovered_project_inputs,
)
from sqltide.compiler.discovery.models import (
    DiscoveredSourceFile,
    LoadedPipeline,
    LoadedProject,
)
from sqltide.compiler.test_discovery.models import LoadedSqlTest


def validate_attached_project_inputs(
    *,
    source_files: tuple[DiscoveredSourceFile, ...],
    loaded_project: LoadedProject | None,
    loaded_pipelines: tuple[LoadedPipeline, ...],
    loaded_tests: tuple[LoadedSqlTest, ...],
    loaded_audits: tuple[LoadedSqlAudit, ...],
) -> None:
    """Reject duplicate identities and invalid effective replay policies."""

    validate_discovered_project_inputs(
        source_files=source_files,
        loaded_project=loaded_project,
        loaded_pipelines=loaded_pipelines,
        loaded_tests=loaded_tests,
        loaded_audits=loaded_audits,
    )
