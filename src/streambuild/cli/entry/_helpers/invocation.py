from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapter.main.resolve_adapter import resolve_adapter
from streambuild.cli.entry._helpers.entrypoint import (
    resolve_optional_int_arg,
    resolve_optional_str_arg,
    resolve_pipelines_root,
    resolve_project_config,
    resolve_project_dir,
    resolved_environment,
)
from streambuild.cli.entry.constants import (
    COMMANDS_REQUIRING_PIPELINES_ROOT,
    DEV_CLI_VARIABLES_ENV_VAR,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.models import (
    CliConnectionOptions,
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
    cli_variables: dict[str, object] = _resolved_cli_variables(args=args, environment=resolved_env)
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
        selected_target=getattr(args, "target", None),
        cli_variables=cli_variables,
        environment=resolved_env,
    )
    adapter: Adapter = resolve_adapter(project_config.adapter_name)
    return ResolvedCliInvocation(
        args=args,
        project_dir=resolved_project_dir,
        pipelines_root=pipelines_root,
        database=getattr(args, "database", None) or project_config.default_database,
        adapter=adapter,
        loaded_project=project_config.loaded_project,
        connection=CliConnectionOptions(
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
            raw_project_connection=project_config.raw_connection,
            variables=project_config.variables,
            environment=resolved_env,
        ),
    )


def _resolved_cli_variables(
    *, args: argparse.Namespace, environment: Mapping[str, str]
) -> dict[str, object]:
    inherited_raw: str | None = environment.get(DEV_CLI_VARIABLES_ENV_VAR)
    inherited: object = {} if inherited_raw is None else json.loads(inherited_raw)
    if not isinstance(inherited, dict):
        raise CliUserError(f"{DEV_CLI_VARIABLES_ENV_VAR} must contain a JSON object")
    return {
        **{str(key): value for key, value in inherited.items()},
        **getattr(args, "vars", {}),
    }
