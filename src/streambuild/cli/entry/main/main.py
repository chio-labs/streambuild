"""Root CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.cli.entry._helpers.clickhouse import (
    build_clickhouse_client_for_connection,
)
from streambuild.cli.entry._helpers.entrypoint import (
    argv_for_parse_args,
    resolve_clickhouse_connection,
    resolve_optional_int_arg,
    resolve_optional_str_arg,
    resolve_pipelines_root,
    resolve_project_config,
    resolve_project_dir,
    resolved_environment,
)
from streambuild.cli.entry._helpers.parser import build_cli_parser
from streambuild.cli.entry.constants import (
    AUDIT_COMMAND,
    BACKFILL_SUBCOMMAND,
    REPAIR_COMMAND,
)
from streambuild.cli.entry.models import (
    CliEntrypointHandlers,
    ResolvedClickHouseConnection,
    ResolvedCliProjectConfig,
)
from streambuild.cli.shared._helpers.errors import render_expected_clickhouse_error
from streambuild.cli.shared.exceptions import CliUserError
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.integrations.clickhouse.client import ClickHouseClient


def main(argv: Sequence[str] | None = None) -> int:
    from streambuild.cli.audit.main.run_audit import run_audit
    from streambuild.cli.audit_backfill.main.run_audit_backfill import run_audit_backfill
    from streambuild.cli.backfill.main.run_backfill import run_backfill
    from streambuild.cli.compile.main.run_compile import run_compile
    from streambuild.cli.discover.main.run_discover import run_discover
    from streambuild.cli.doctor.main.run_doctor import run_doctor
    from streambuild.cli.janitor.main.run_janitor import run_janitor
    from streambuild.cli.plan.main.run_plan import run_plan
    from streambuild.cli.publish.main.run_publish import run_publish
    from streambuild.cli.reconcile.main.run_reconcile import run_reconcile
    from streambuild.cli.repair_active_view.main.run_repair_active_view import (
        run_repair_active_view,
    )
    from streambuild.cli.test.main.run_test import run_test

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_discover=run_discover,
        run_compile=run_compile,
        run_test=run_test,
        run_audit=run_audit,
        run_plan=run_plan,
        run_backfill=run_backfill,
        run_audit_backfill=run_audit_backfill,
        run_publish=run_publish,
        run_reconcile=run_reconcile,
        run_janitor=run_janitor,
        run_doctor=run_doctor,
        run_repair_active_view=run_repair_active_view,
    )
    return _main_with_dependencies(argv=argv, handlers=handlers)


def _main_with_dependencies(
    *,
    argv: Sequence[str] | None = None,
    handlers: CliEntrypointHandlers,
    environment: Mapping[str, str] | None = None,
    working_directory: Path | None = None,
    clickhouse_client: ClickHouseClient | None = None,
) -> int:
    parser: argparse.ArgumentParser = build_cli_parser()
    args: argparse.Namespace = parser.parse_args(argv_for_parse_args(argv))
    resolved_database: str | None = None
    try:
        resolved_env: Mapping[str, str] = resolved_environment(environment)
        current_working_directory: Path = (
            Path.cwd() if working_directory is None else working_directory
        )
        resolved_project_dir: Path | None = resolve_project_dir(
            project_dir=getattr(args, "project_dir", None),
            working_directory=current_working_directory,
        )
        needs_pipelines_root: bool = (
            args.command
            in {
                "discover",
                "compile",
                "test",
                "plan",
                "backfill",
                "reconcile",
            }
            or args.command == AUDIT_COMMAND
        )
        pipelines_root: Path | None = (
            resolve_pipelines_root(
                project_dir=getattr(args, "project_dir", None),
                working_directory=current_working_directory,
            )
            if needs_pipelines_root
            else None
        )
        project_config: ResolvedCliProjectConfig = resolve_project_config(
            pipelines_root=pipelines_root,
            project_dir=resolved_project_dir,
            working_directory=current_working_directory,
        )
        resolved_host: str | None = resolve_optional_str_arg(
            value=getattr(args, "host", None),
            env_var_name="STREAMBUILD_CLICKHOUSE_HOST",
            environment=resolved_env,
        )
        resolved_port: int | None = resolve_optional_int_arg(
            value=getattr(args, "port", None),
            env_var_name="STREAMBUILD_CLICKHOUSE_PORT",
            environment=resolved_env,
        )
        resolved_username: str | None = resolve_optional_str_arg(
            value=getattr(args, "username", None),
            env_var_name="STREAMBUILD_CLICKHOUSE_USERNAME",
            environment=resolved_env,
        )
        resolved_password: str | None = resolve_optional_str_arg(
            value=getattr(args, "password", None),
            env_var_name="STREAMBUILD_CLICKHOUSE_PASSWORD",
            environment=resolved_env,
        )
        if args.command == "discover":
            return handlers.run_discover(pipelines_root=pipelines_root)
        if args.command == "compile":
            return handlers.run_compile(
                pipelines_root=pipelines_root,
                target_dir=(
                    getattr(args, "target_dir", None)
                    or (
                        resolved_project_dir / "target"
                        if resolved_project_dir is not None
                        else None
                    )
                ),
            )
        resolved_database = getattr(args, "database", None) or project_config.default_database
        connection: ResolvedClickHouseConnection | None = None
        if clickhouse_client is None:
            connection = resolve_clickhouse_connection(
                host=resolved_host,
                port=resolved_port,
                username=resolved_username,
                password=resolved_password,
                project_connection=project_config.connection,
            )

        def resolved_client() -> ClickHouseClient:
            if clickhouse_client is not None:
                return clickhouse_client
            if connection is None:
                raise CliUserError("CLI entrypoint failed to resolve a ClickHouse connection")
            return build_clickhouse_client_for_connection(connection=connection)

        if args.command == "test":
            return handlers.run_test(
                pipelines_root=pipelines_root,
                project_dir=resolved_project_dir,
                selectors=tuple(getattr(args, "select", [])),
                paths=tuple(getattr(args, "paths", ())),
                verbose=bool(getattr(args, "verbose", False)),
                client=resolved_client(),
            )

        if args.command == BACKFILL_SUBCOMMAND:
            return handlers.run_backfill(
                pipelines_root=pipelines_root,
                database=resolved_database,
                metadata_database=getattr(args, "metadata_database", None),
                selectors=tuple(getattr(args, "select", [])),
                deployment_id=getattr(args, "deployment_id", None),
                full_refresh=bool(getattr(args, "full_refresh", False)),
                start_time=getattr(args, "start_time", None),
                json_output=bool(getattr(args, "json", False)),
                verbose=bool(getattr(args, "verbose", False)),
                auto_approve=bool(getattr(args, "auto_approve", False)),
                client=resolved_client(),
            )
        if args.command == AUDIT_COMMAND:
            if getattr(args, "audit_command", None) == BACKFILL_SUBCOMMAND:
                return handlers.run_audit_backfill(
                    pipelines_root=pipelines_root,
                    project_dir=(
                        resolved_project_dir
                        if resolved_project_dir is not None
                        else (pipelines_root.parent if pipelines_root is not None else None)
                    ),
                    database=resolved_database,
                    metadata_database=getattr(args, "metadata_database", None),
                    deployment_id=getattr(args, "deployment_id", None),
                    json_output=bool(getattr(args, "json", False)),
                    client=resolved_client(),
                )
            if pipelines_root is None:
                raise CliUserError("Audit command requires a resolved pipelines root")
            return handlers.run_audit(
                pipelines_root=pipelines_root,
                project_dir=resolved_project_dir or pipelines_root.parent,
                database=resolved_database,
                selectors=tuple(getattr(args, "select", [])),
                json_output=bool(getattr(args, "json", False)),
                client=resolved_client(),
            )
        if args.command == "publish":
            return handlers.run_publish(
                database=resolved_database,
                metadata_database=getattr(args, "metadata_database", None),
                deployment_id=getattr(args, "deployment_id", None),
                json_output=bool(getattr(args, "json", False)),
                client=resolved_client(),
            )
        if args.command == "reconcile":
            return handlers.run_reconcile(
                pipelines_root=pipelines_root,
                database=resolved_database,
                metadata_database=getattr(args, "metadata_database", None),
                selectors=tuple(getattr(args, "select", [])),
                json_output=bool(getattr(args, "json", False)),
                apply=bool(getattr(args, "apply", False)),
                client=resolved_client(),
            )
        if args.command == "doctor":
            return handlers.run_doctor(
                database=resolved_database,
                client=resolved_client(),
            )
        if args.command == "janitor":
            return handlers.run_janitor(
                database=resolved_database,
                retention_days=args.retention_days,
                apply=bool(getattr(args, "apply", False)),
                json_output=bool(getattr(args, "json", False)),
                client=resolved_client(),
            )
        if args.command == REPAIR_COMMAND:
            return handlers.run_repair_active_view(
                database=resolved_database,
                table=args.table,
                deployment_id=args.deployment_id,
                client=resolved_client(),
            )
        return handlers.run_plan(
            pipelines_root=pipelines_root,
            database=resolved_database,
            selectors=tuple(getattr(args, "select", [])),
            full_refresh=bool(getattr(args, "full_refresh", False)),
            start_time=getattr(args, "start_time", None),
            json_output=bool(getattr(args, "json", False)),
            verbose=bool(getattr(args, "verbose", False)),
            client=resolved_client(),
        )
    except CliUserError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (TransformSqlContractError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (DatabaseError, OperationalError) as error:
        rendered_error: str | None = render_expected_clickhouse_error(
            command_name=_command_name(args),
            database=resolved_database or "<unknown>",
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise


def _command_name(args: argparse.Namespace) -> str:
    if (
        args.command == AUDIT_COMMAND
        and getattr(args, "audit_command", None) == BACKFILL_SUBCOMMAND
    ):
        return "audit backfill"
    if args.command == AUDIT_COMMAND:
        return "audit"
    if args.command == REPAIR_COMMAND:
        return "repair active-view"
    return str(args.command)
