"""Resolve the effective default database for a command."""

from __future__ import annotations

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._project_default_database import (
    project_default_database,
)
from streambuild.compiler.discovery.models import LoadedPipeline


def resolve_default_database(
    *, loaded_pipelines: list[LoadedPipeline], override: str | None
) -> str:
    if override is not None:
        return override

    project_database: str | None = project_default_database(loaded_pipelines)
    if project_database is not None:
        return project_database

    raise CliUserError(
        "No database was provided. Pass --database or define database on the selected "
        "target in streambuild_project.toml"
    )
