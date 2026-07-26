from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from streambuild.cli.commands.main.entry.models import (
    ResolvedClickHouseConnection,
    ResolvedCliProjectConfig,
)
from streambuild.cli.commands.main.shared.exceptions import CliUserError
from streambuild.compiler.discovery._helpers.load import load_project_for_path
from streambuild.spec.models.project import Project


def argv_for_parse_args(argv: Sequence[str] | None) -> list[str] | None:
    if argv is None:
        return None
    return list(argv[1:])


def resolved_environment(environment: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environment is None else environment


def resolve_optional_str_arg(
    *,
    value: str | None,
    env_var_name: str,
    environment: Mapping[str, str],
) -> str | None:
    if value is not None:
        return value
    env_value: str | None = environment.get(env_var_name)
    if not env_value:
        return None
    return env_value


def resolve_optional_int_arg(
    *,
    value: int | None,
    env_var_name: str,
    environment: Mapping[str, str],
) -> int | None:
    if value is not None:
        return value
    env_value: str | None = environment.get(env_var_name)
    if not env_value:
        return None
    return int(env_value)


def resolve_project_config(
    *,
    pipelines_root: Path | None,
    project_dir: Path | None,
    working_directory: Path,
) -> ResolvedCliProjectConfig:
    project: Project | None = load_project_for_path(
        pipelines_root
        if pipelines_root is not None
        else project_dir
        if project_dir is not None
        else working_directory
    )
    if project is None or project.clickhouse is None:
        return ResolvedCliProjectConfig(
            connection=None,
            default_database=None if project is None else project.default_database,
            project=project,
        )
    return ResolvedCliProjectConfig(
        connection=ResolvedClickHouseConnection(
            host=project.clickhouse.host,
            port=project.clickhouse.port,
            username=project.clickhouse.username,
            password=project.clickhouse.password,
        ),
        default_database=project.default_database,
        project=project,
    )


def resolve_pipelines_root(
    *,
    project_dir: Path | None,
    working_directory: Path,
) -> Path:
    resolved_project_dir: Path | None = resolve_project_dir(
        project_dir=project_dir,
        working_directory=working_directory,
    )
    current_directory: Path = (
        working_directory if resolved_project_dir is None else resolved_project_dir
    )
    current_directory = current_directory.resolve()
    if project_dir is not None:
        direct_pipelines_root: Path = current_directory / "pipelines"
        if direct_pipelines_root.exists():
            return direct_pipelines_root
        if current_directory.exists():
            return current_directory
    while True:
        project_file: Path = current_directory / "streambuild_project.yml"
        pipelines_root: Path = current_directory / "pipelines"
        if project_file.exists():
            if not pipelines_root.exists():
                raise CliUserError(
                    f"Found StreamBuild project at '{current_directory}', but '{pipelines_root}' "
                    "does not exist"
                )
            return pipelines_root
        if project_dir is not None:
            break
        if current_directory.parent == current_directory:
            break
        current_directory = current_directory.parent
    raise CliUserError(
        "No StreamBuild project found from the current directory. "
        "Run this command inside a project or pass --project-dir."
    )


def resolve_project_dir(
    *,
    project_dir: Path | None,
    working_directory: Path,
) -> Path | None:
    if project_dir is None:
        return None
    if project_dir.is_absolute():
        return project_dir
    return working_directory / project_dir


def require_str_arg(*, value: str | None, arg_name: str, env_var_name: str) -> str:
    if value is None:
        raise CliUserError(f"Missing {arg_name}. Pass --{arg_name} or set {env_var_name}.")
    return value


def require_int_arg(*, value: int | None, arg_name: str, env_var_name: str) -> int:
    if value is None:
        raise CliUserError(f"Missing {arg_name}. Pass --{arg_name} or set {env_var_name}.")
    return value


def resolve_clickhouse_connection(
    *,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    project_connection: ResolvedClickHouseConnection | None,
) -> ResolvedClickHouseConnection:
    return ResolvedClickHouseConnection(
        host=require_str_arg(
            value=host
            if host is not None
            else None
            if project_connection is None
            else project_connection.host,
            arg_name="host",
            env_var_name="STREAMBUILD_CLICKHOUSE_HOST",
        ),
        port=require_int_arg(
            value=port
            if port is not None
            else None
            if project_connection is None
            else project_connection.port,
            arg_name="port",
            env_var_name="STREAMBUILD_CLICKHOUSE_PORT",
        ),
        username=require_str_arg(
            value=username
            if username is not None
            else None
            if project_connection is None
            else project_connection.username,
            arg_name="username",
            env_var_name="STREAMBUILD_CLICKHOUSE_USERNAME",
        ),
        password=require_str_arg(
            value=password
            if password is not None
            else None
            if project_connection is None
            else project_connection.password,
            arg_name="password",
            env_var_name="STREAMBUILD_CLICKHOUSE_PASSWORD",
        ),
    )
