from __future__ import annotations

from streambuild.cli.shared.exceptions import CliUserError
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models import Project


def resolve_default_database(
    *, loaded_pipelines: list[LoadedPipeline], override: str | None
) -> str:
    if override is not None:
        return override

    project_database: str | None = project_default_database(loaded_pipelines)
    if project_database is not None:
        return project_database

    raise CliUserError(
        "No database was provided. Pass --database or define "
        "default_database in streambuild_project.yml"
    )


def project_default_database(loaded_pipelines: list[LoadedPipeline]) -> str | None:
    declared_databases: tuple[str, ...] = _declared_default_databases(
        loaded_pipelines=loaded_pipelines
    )
    if not declared_databases:
        return None
    if len(set(declared_databases)) > 1:
        raise CliUserError("Discovered pipelines disagree on project default_database")
    return declared_databases[0]


def _declared_default_databases(*, loaded_pipelines: list[LoadedPipeline]) -> tuple[str, ...]:
    databases: list[str] = []
    loaded_pipeline: LoadedPipeline
    for loaded_pipeline in loaded_pipelines:
        project: Project | None = loaded_pipeline.project
        if project is not None and project.default_database is not None:
            databases.append(project.default_database)
    return tuple(databases)
