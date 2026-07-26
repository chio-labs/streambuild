from __future__ import annotations

import argparse
from pathlib import Path

from streambuild.cli.backfill.models import BackfillCommandOptions
from streambuild.cli.entry._helpers.clickhouse import build_clickhouse_client_for_connection
from streambuild.cli.entry._helpers.entrypoint import resolve_clickhouse_connection
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.models import (
    CliEntrypointHandlers,
    ResolvedClickHouseConnection,
    ResolvedCliInvocation,
)
from streambuild.cli.entry.types import CliCommand, CliSubcommand
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def dispatch_cli_command(
    *,
    invocation: ResolvedCliInvocation,
    handlers: CliEntrypointHandlers,
    clickhouse_client: ClickHouseClient | None,
) -> int:
    args: argparse.Namespace = invocation.args
    if args.command == CliCommand.DISCOVER:
        return handlers.run_discover(pipelines_root=invocation.pipelines_root)
    if args.command == CliCommand.COMPILE:
        return handlers.run_compile(
            pipelines_root=invocation.pipelines_root,
            target_dir=(
                getattr(args, "target_dir", None)
                or (
                    invocation.project_dir / "target"
                    if invocation.project_dir is not None
                    else None
                )
            ),
        )
    client: ClickHouseClient = _resolve_client(
        invocation=invocation,
        clickhouse_client=clickhouse_client,
    )
    if args.command == CliCommand.TEST:
        return handlers.run_test(
            pipelines_root=invocation.pipelines_root,
            project_dir=invocation.project_dir,
            selectors=tuple(getattr(args, "select", [])),
            paths=tuple(getattr(args, "paths", ())),
            verbose=bool(getattr(args, "verbose", False)),
            client=client,
        )
    if args.command == CliSubcommand.BACKFILL:
        return handlers.run_backfill(
            options=BackfillCommandOptions(
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
            ),
            client=client,
        )
    if args.command == CliCommand.AUDIT:
        if getattr(args, "audit_command", None) == CliSubcommand.BACKFILL:
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
        pipelines_root=invocation.pipelines_root,
        database=invocation.database,
        selectors=tuple(getattr(args, "select", [])),
        full_refresh=bool(getattr(args, "full_refresh", False)),
        start_time=getattr(args, "start_time", None),
        json_output=bool(getattr(args, "json", False)),
        verbose=bool(getattr(args, "verbose", False)),
        client=client,
    )


def _resolve_client(
    *,
    invocation: ResolvedCliInvocation,
    clickhouse_client: ClickHouseClient | None,
) -> ClickHouseClient:
    if clickhouse_client is not None:
        return clickhouse_client
    connection: ResolvedClickHouseConnection = resolve_clickhouse_connection(
        host=invocation.clickhouse.host,
        port=invocation.clickhouse.port,
        username=invocation.clickhouse.username,
        password=invocation.clickhouse.password,
        project_connection=invocation.clickhouse.project_connection,
    )
    return build_clickhouse_client_for_connection(connection=connection)


def _require_pipelines_root(invocation: ResolvedCliInvocation) -> Path:
    if invocation.pipelines_root is None:
        raise CliUserError("Backfill command requires a resolved pipelines root")
    return invocation.pipelines_root
