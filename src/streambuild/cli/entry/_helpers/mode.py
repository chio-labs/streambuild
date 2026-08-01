from __future__ import annotations

import argparse

from streambuild.cli.entry.constants import (
    DIRECT_ONLY_COMMANDS,
    VIRTUAL_ENVIRONMENT_ONLY_COMMANDS,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.models import ResolvedCliInvocation
from streambuild.cli.entry.types import CliCommand, CliSubcommand
from streambuild.compiler.discovery.models import LoadedProject


def validate_cli_command_mode(*, invocation: ResolvedCliInvocation) -> None:
    """Reject mode-specific commands before credentials or warehouse IO are resolved."""

    command: CliCommand = CliCommand(invocation.args.command)
    virtual_environments: bool = _virtual_environments_enabled(invocation.loaded_project)
    if command in DIRECT_ONLY_COMMANDS and virtual_environments:
        raise CliUserError(
            f"stb {command.value} is unavailable while virtual environments are enabled. "
            "Disable settings.virtual_environments in streambuild_project.toml or "
            "streambuild_local.toml for this invocation."
        )
    if _is_virtual_environment_only(args=invocation.args) and not virtual_environments:
        raise CliUserError(
            f"stb {_command_display(args=invocation.args)} requires virtual environments to be "
            "enabled. Set settings.virtual_environments = true in streambuild_project.toml or "
            "streambuild_local.toml for this invocation."
        )


def _virtual_environments_enabled(loaded_project: LoadedProject | None) -> bool:
    return bool(
        loaded_project is not None
        and loaded_project.effective_configuration is not None
        and loaded_project.effective_configuration.settings.virtual_environments
    )


def _is_virtual_environment_only(*, args: argparse.Namespace) -> bool:
    command: CliCommand = CliCommand(args.command)
    return command in VIRTUAL_ENVIRONMENT_ONLY_COMMANDS or (
        command == CliCommand.AUDIT
        and getattr(args, "audit_command", None) == CliSubcommand.DEPLOYMENT
    )


def _command_display(*, args: argparse.Namespace) -> str:
    if args.command == CliCommand.AUDIT:
        return "audit deployment"
    if args.command == CliCommand.REPAIR:
        return "repair active-view"
    return str(args.command)
