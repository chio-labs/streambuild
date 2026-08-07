"""Root CLI entrypoint."""

from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import FrameType

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError, AdapterWarehouseError
from streambuild.cli.entry._helpers.adapter_connection import (
    resolve_invocation_connection,
)
from streambuild.cli.entry._helpers.dispatch import dispatch_cli_command
from streambuild.cli.entry._helpers.entrypoint import (
    argv_for_parse_args,
    raise_keyboard_interrupt_from_signal,
)
from streambuild.cli.entry._helpers.invocation import resolve_cli_invocation
from streambuild.cli.entry._helpers.mode import validate_cli_command_mode
from streambuild.cli.entry._helpers.parser import build_cli_parser
from streambuild.cli.entry.constants import DISPLAY_NAME_BY_COMMAND
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._errors import render_expected_warehouse_error
from streambuild.cli.entry.models import (
    CliEntrypointHandlers,
    ResolvedCliInvocation,
    ResolvedInvocationConnection,
)
from streambuild.cli.entry.types import CliCommand
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.diagnostics.main.attach_error_diagnostic import attach_error_diagnostic
from streambuild.diagnostics.main.render_error import render_error
from streambuild.diagnostics.types import DiagnosticPhase


def main(argv: Sequence[str] | None = None) -> int:
    from streambuild.cli.audit.main._run_audit import run_audit
    from streambuild.cli.build.main._run_build import run_build
    from streambuild.cli.compile.main._run_compile import run_compile
    from streambuild.cli.deployment.main._run_deployment_list import run_deployment_list
    from streambuild.cli.deployment.main._run_deployment_show import run_deployment_show
    from streambuild.cli.dev.main._run_dev import run_dev
    from streambuild.cli.discover.main._run_discover import run_discover
    from streambuild.cli.doctor.main._run_doctor import run_doctor
    from streambuild.cli.janitor.main._run_janitor import run_janitor
    from streambuild.cli.plan.main._run_plan import run_plan
    from streambuild.cli.promotion.main._run_deployment_promotion import (
        run_deployment_promotion,
    )
    from streambuild.cli.readiness.main._run_deployment_audit import run_deployment_audit
    from streambuild.cli.reconcile.main._run_reconcile import run_reconcile
    from streambuild.cli.repair_active_view.main._run_repair_active_view import (
        run_repair_active_view,
    )
    from streambuild.cli.test.main._run_test import run_test

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_discover=run_discover,
        run_compile=run_compile,
        run_test=run_test,
        run_audit=run_audit,
        run_plan=run_plan,
        run_build=run_build,
        run_deployment_list=run_deployment_list,
        run_deployment_show=run_deployment_show,
        run_deployment_audit=run_deployment_audit,
        run_deployment_promote=run_deployment_promotion,
        run_reconcile=run_reconcile,
        run_janitor=run_janitor,
        run_doctor=run_doctor,
        run_dev=run_dev,
        run_repair_active_view=run_repair_active_view,
    )
    previous_sigterm_handler: Callable[[int, FrameType | None], object] | int | None = (
        signal.getsignal(signal.SIGTERM)
    )
    signal.signal(signal.SIGTERM, raise_keyboard_interrupt_from_signal)
    try:
        return _main_with_dependencies(argv=argv, handlers=handlers)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


def _main_with_dependencies(
    *,
    argv: Sequence[str] | None = None,
    handlers: CliEntrypointHandlers,
    environment: Mapping[str, str] | None = None,
    working_directory: Path | None = None,
    adapter_connection: AdapterConnection | None = None,
    observation_adapter_connection: AdapterConnection | None = None,
) -> int:
    parser: argparse.ArgumentParser = build_cli_parser()
    args: argparse.Namespace = parser.parse_args(argv_for_parse_args(argv))
    resolved_database: str | None = None
    try:
        invocation: ResolvedCliInvocation = resolve_cli_invocation(
            args=args,
            environment=environment,
            working_directory=working_directory,
        )
        validate_cli_command_mode(invocation=invocation)
        resolved_database = invocation.database
        resolved_connection: ResolvedInvocationConnection = resolve_invocation_connection(
            invocation=invocation,
            provided_connection=adapter_connection,
        )
        observation_connection: ResolvedInvocationConnection | None = None
        try:
            if adapter_connection is None and args.command == CliCommand.BUILD:
                observation_connection = resolve_invocation_connection(
                    invocation=invocation, provided_connection=None
                )
            if adapter_connection is not None and args.command == CliCommand.BUILD:
                if observation_adapter_connection is None:
                    raise CliUserError("Build requires a dedicated observation connection")
                observation_connection = ResolvedInvocationConnection(
                    connection=observation_adapter_connection,
                    close_after_command=False,
                )
            return dispatch_cli_command(
                invocation=invocation,
                handlers=handlers,
                adapter_connection=resolved_connection.connection,
                observation_connection=(
                    None if observation_connection is None else observation_connection.connection
                ),
            )
        finally:
            if (
                observation_connection is not None
                and observation_connection.close_after_command
                and observation_connection.connection is not None
            ):
                observation_connection.connection.close()
            if (
                resolved_connection.close_after_command
                and resolved_connection.connection is not None
            ):
                resolved_connection.connection.close()
    except CliUserError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (TransformSqlContractError, ValueError) as error:
        print(render_error(error), file=sys.stderr)
        return 1
    except AdapterWarehouseError as error:
        rendered_error: str | None = render_expected_warehouse_error(
            command_name=_command_name(args),
            database=resolved_database or "<unknown>",
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise
    except AdapterError as error:
        _ = attach_error_diagnostic(
            error=error,
            phase=DiagnosticPhase.RUNTIME,
            code="STB-RUNTIME-001",
        )
        print(render_error(error), file=sys.stderr)
        return 1


def _command_name(args: argparse.Namespace) -> str:
    """Return the operator-facing command name for error messages."""

    if args.command == CliCommand.DEPLOYMENT:
        return f"deployment {args.deployment_command}"
    return DISPLAY_NAME_BY_COMMAND.get(args.command, str(args.command))
