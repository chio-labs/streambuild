"""Return the project-declared default database, if any."""

from __future__ import annotations

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.discovery.models import LoadedPipeline
from streambuild.spec.models import Project


def _declared_default_databases(*, loaded_pipelines: list[LoadedPipeline]) -> tuple[str, ...]:
    databases: list[str] = []
    loaded_pipeline: LoadedPipeline
    for loaded_pipeline in loaded_pipelines:
        project: Project | None = loaded_pipeline.project
        if project is not None and project.default_database is not None:
            databases.append(project.default_database)
    return tuple(databases)


def project_default_database(loaded_pipelines: list[LoadedPipeline]) -> str | None:
    declared_databases: tuple[str, ...] = _declared_default_databases(
        loaded_pipelines=loaded_pipelines
    )
    if not declared_databases:
        return None
    if len(set(declared_databases)) > 1:
        raise CliUserError("Discovered pipelines disagree on project default_database")
    return declared_databases[0]
