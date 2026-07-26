from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from streambuild.cli.entry._helpers.entrypoint import (
    resolve_optional_int_arg,
    resolve_optional_str_arg,
    resolve_pipelines_root,
    resolve_project_config,
    resolve_project_dir,
    resolved_environment,
)
from streambuild.cli.entry.constants import COMMANDS_REQUIRING_PIPELINES_ROOT
from streambuild.cli.entry.models import (
    CliClickHouseOptions,
    ResolvedCliInvocation,
    ResolvedCliProjectConfig,
)


def resolve_cli_invocation(
    *,
    args: argparse.Namespace,
    environment: Mapping[str, str] | None,
    working_directory: Path | None,
) -> ResolvedCliInvocation:
    resolved_env: Mapping[str, str] = resolved_environment(environment)
    current_working_directory: Path = Path.cwd() if working_directory is None else working_directory
    project_dir_arg: Path | None = getattr(args, "project_dir", None)
    resolved_project_dir: Path | None = resolve_project_dir(
        project_dir=project_dir_arg,
        working_directory=current_working_directory,
    )
    pipelines_root: Path | None = (
        resolve_pipelines_root(
            project_dir=project_dir_arg,
            working_directory=current_working_directory,
        )
        if args.command in COMMANDS_REQUIRING_PIPELINES_ROOT
        else None
    )
    project_config: ResolvedCliProjectConfig = resolve_project_config(
        pipelines_root=pipelines_root,
        project_dir=resolved_project_dir,
        working_directory=current_working_directory,
    )
    return ResolvedCliInvocation(
        args=args,
        project_dir=resolved_project_dir,
        pipelines_root=pipelines_root,
        database=getattr(args, "database", None) or project_config.default_database,
        clickhouse=CliClickHouseOptions(
            host=resolve_optional_str_arg(
                value=getattr(args, "host", None),
                env_var_name="STREAMBUILD_CLICKHOUSE_HOST",
                environment=resolved_env,
            ),
            port=resolve_optional_int_arg(
                value=getattr(args, "port", None),
                env_var_name="STREAMBUILD_CLICKHOUSE_PORT",
                environment=resolved_env,
            ),
            username=resolve_optional_str_arg(
                value=getattr(args, "username", None),
                env_var_name="STREAMBUILD_CLICKHOUSE_USERNAME",
                environment=resolved_env,
            ),
            password=resolve_optional_str_arg(
                value=getattr(args, "password", None),
                env_var_name="STREAMBUILD_CLICKHOUSE_PASSWORD",
                environment=resolved_env,
            ),
            project_connection=project_config.connection,
        ),
    )
