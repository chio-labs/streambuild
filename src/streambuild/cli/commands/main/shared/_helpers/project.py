from __future__ import annotations

from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models.project import Project


def resolve_default_database(
    *, loaded_pipelines: list[LoadedPipeline], override: str | None
) -> str:
    if override is not None:
        return override

    project_database: str | None = project_default_database(loaded_pipelines)
    if project_database is not None:
        return project_database

    raise ValueError(
        "No database was provided. Pass --database or define "
        "default_database in streambuild_project.yml"
    )


def project_default_database(loaded_pipelines: list[LoadedPipeline]) -> str | None:
    project_databases: set[str] = {
        project.default_database
        for project in [loaded_pipeline.project for loaded_pipeline in loaded_pipelines]
        if project is not None and project.default_database is not None
    }
    if not project_databases:
        return None
    if len(project_databases) > 1:
        raise ValueError("Discovered pipelines disagree on project default_database")

    project: Project = next(
        project
        for project in [loaded_pipeline.project for loaded_pipeline in loaded_pipelines]
        if project is not None and project.default_database is not None
    )
    return project.default_database
