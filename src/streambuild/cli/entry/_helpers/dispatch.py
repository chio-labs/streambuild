from __future__ import annotations

import argparse
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.build.models import BuildCommandOptions
from streambuild.cli.dev.models import DevCommandOptions
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.models import (
    CliEntrypointHandlers,
    ResolvedCliInvocation,
)
from streambuild.cli.entry.types import CliCommand, CliSubcommand
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.dev_server.constants import DEFAULT_DEV_SERVER_HOST, DEFAULT_DEV_SERVER_PORT


def dispatch_cli_command(
    *,
    invocation: ResolvedCliInvocation,
    handlers: CliEntrypointHandlers,
    adapter_connection: AdapterConnection | None,
) -> int:
    args: argparse.Namespace = invocation.args
    adapter_profile: CompilerAdapterProfile = build_compiler_adapter_profile(invocation.adapter)
    if args.command == CliCommand.DISCOVER:
        return handlers.run_discover(
            pipelines_root=invocation.pipelines_root,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
        )
    if args.command == CliCommand.COMPILE:
        return handlers.run_compile(
            pipelines_root=invocation.pipelines_root,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
            target_dir=(
                getattr(args, "target_dir", None)
                or (
                    invocation.project_dir / "target"
                    if invocation.project_dir is not None
                    else None
                )
            ),
        )
    client: AdapterConnection = _resolve_connection(
        adapter_connection=adapter_connection,
    )
    if args.command == CliCommand.DEV:
        return handlers.run_dev(
            options=DevCommandOptions(
                pipelines_root=_require_pipelines_root(invocation),
                database=invocation.database,
                host=str(getattr(args, "ui_host", DEFAULT_DEV_SERVER_HOST)),
                port=int(getattr(args, "ui_port", DEFAULT_DEV_SERVER_PORT)),
            ),
            client=client,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
        )
    if args.command == CliCommand.TEST:
        return handlers.run_test(
            pipelines_root=invocation.pipelines_root,
            project_dir=invocation.project_dir,
            selectors=tuple(getattr(args, "select", [])),
            paths=tuple(getattr(args, "paths", ())),
            verbose=bool(getattr(args, "verbose", False)),
            client=client,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
            target_dir=getattr(args, "target_dir", None),
            database=invocation.database or "",
        )
    if args.command == CliCommand.BUILD:
        return handlers.run_build(
            options=BuildCommandOptions(
                pipelines_root=_require_pipelines_root(invocation),
                database=invocation.database,
                metadata_database=getattr(args, "metadata_database", None),
                selectors=tuple(getattr(args, "select", [])),
                deployment_id=getattr(args, "deployment_id", None),
                full_refresh=bool(getattr(args, "full_refresh", False)),
                start_time=getattr(args, "start_time", None),
                json_output=bool(getattr(args, "json", False)),
                verbose=bool(getattr(args, "verbose", False)),
                auto_approve=bool(getattr(args, "auto_approve", False)),
                events_output=bool(getattr(args, "events", False)),
            ),
            client=client,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
        )
    if args.command == CliCommand.AUDIT:
        if getattr(args, "audit_command", None) == CliSubcommand.DEPLOYMENT:
            return handlers.run_audit_backfill(
                pipelines_root=invocation.pipelines_root,
                project_dir=(
                    invocation.project_dir
                    if invocation.project_dir is not None
                    else (
                        invocation.pipelines_root.parent
                        if invocation.pipelines_root is not None
                        else None
                    )
                ),
                database=invocation.database,
                metadata_database=getattr(args, "metadata_database", None),
                deployment_id=getattr(args, "deployment_id", None),
                json_output=bool(getattr(args, "json", False)),
                client=client,
                loaded_project=invocation.loaded_project,
                adapter_profile=adapter_profile,
            )
        if invocation.pipelines_root is None:
            raise CliUserError("Audit command requires a resolved pipelines root")
        return handlers.run_audit(
            pipelines_root=invocation.pipelines_root,
            project_dir=invocation.project_dir or invocation.pipelines_root.parent,
            database=invocation.database,
            selectors=tuple(getattr(args, "select", [])),
            json_output=bool(getattr(args, "json", False)),
            client=client,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
        )
    if args.command == CliCommand.PUBLISH:
        return handlers.run_publish(
            database=invocation.database,
            metadata_database=getattr(args, "metadata_database", None),
            deployment_id=getattr(args, "deployment_id", None),
            json_output=bool(getattr(args, "json", False)),
            client=client,
        )
    if args.command == CliCommand.RECONCILE:
        return handlers.run_reconcile(
            pipelines_root=invocation.pipelines_root,
            database=invocation.database,
            metadata_database=getattr(args, "metadata_database", None),
            selectors=tuple(getattr(args, "select", [])),
            json_output=bool(getattr(args, "json", False)),
            apply=bool(getattr(args, "apply", False)),
            client=client,
            loaded_project=invocation.loaded_project,
            adapter_profile=adapter_profile,
        )
    if args.command == CliCommand.DOCTOR:
        return handlers.run_doctor(database=invocation.database, client=client)
    if args.command == CliCommand.JANITOR:
        return handlers.run_janitor(
            database=invocation.database,
            retention_days=args.retention_days,
            apply=bool(getattr(args, "apply", False)),
            json_output=bool(getattr(args, "json", False)),
            client=client,
        )
    if args.command == CliCommand.REPAIR:
        return handlers.run_repair_active_view(
            database=invocation.database,
            table=args.table,
            deployment_id=args.deployment_id,
            client=client,
        )
    return handlers.run_plan(
        options=PlanCommandOptions(
            pipelines_root=_require_pipelines_root(invocation),
            database=invocation.database,
            selectors=tuple(getattr(args, "select", [])),
            full_refresh=bool(getattr(args, "full_refresh", False)),
            start_time=getattr(args, "start_time", None),
            deployment_id=getattr(args, "deployment_id", None),
            json_output=bool(getattr(args, "json", False)),
            verbose=bool(getattr(args, "verbose", False)),
        ),
        client=client,
        loaded_project=invocation.loaded_project,
        adapter_profile=adapter_profile,
    )


def _resolve_connection(
    *,
    adapter_connection: AdapterConnection | None,
) -> AdapterConnection:
    if adapter_connection is None:
        raise CliUserError("Command requires a resolved adapter connection")
    return adapter_connection


def _require_pipelines_root(invocation: ResolvedCliInvocation) -> Path:
    if invocation.pipelines_root is None:
        raise CliUserError("Command requires a resolved pipelines root")
    return invocation.pipelines_root
