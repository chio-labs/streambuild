"""Root-entry safety gates for destructive commands."""

import argparse
import sys

from sqltide.cli.entry.exceptions import CliUserError
from sqltide.cli.entry.types import CliCommand


def require_interactive_destruction(*, args: argparse.Namespace) -> None:
    """Reject destructive commands before project or connection resolution."""

    if args.command in {CliCommand.DESTROY, CliCommand.RESET_TARGET} and not sys.stdin.isatty():
        raise CliUserError(
            f"sqt {args.command} requires an interactive terminal; stdin is not a TTY"
        )
