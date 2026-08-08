from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from streambuild.cli.entry.constants import (
    DIRECT_ONLY_COMMANDS,
    VIRTUAL_ENVIRONMENT_ONLY_COMMANDS,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.models import ResolvedCliInvocation
from streambuild.cli.entry.types import CliCommand
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.discovery.types import PipelineMode


def validate_cli_command_mode(*, invocation: ResolvedCliInvocation) -> None:
    """Reject mode-specific commands before credentials or warehouse IO are resolved."""

    command: CliCommand = CliCommand(invocation.args.command)
    virtual_environments: bool = _virtual_environments_enabled(invocation)
    if command in DIRECT_ONLY_COMMANDS and virtual_environments:
        raise CliUserError(
            f"stb {command.value} is unavailable while virtual environments are enabled. "
            "Set defaults.pipeline_mode = 'direct' in streambuild_project.toml or "
            "streambuild_local.toml for this invocation."
        )
    if _is_virtual_environment_only(args=invocation.args) and not virtual_environments:
        raise CliUserError(
            f"stb {_command_display(args=invocation.args)} requires virtual environments to be "
            "enabled. Set defaults.pipeline_mode = 'virtual' in streambuild_project.toml or "
            "set mode = 'virtual' in a pipeline.toml."
        )


def _virtual_environments_enabled(invocation: ResolvedCliInvocation) -> bool:
    loaded_project: LoadedProject | None = invocation.loaded_project
    if bool(
        loaded_project is not None
        and loaded_project.effective_configuration is not None
        and loaded_project.effective_configuration.defaults.pipeline_mode == PipelineMode.VIRTUAL
    ):
        return True
    pipelines_root: Path | None = invocation.pipelines_root
    if pipelines_root is None and invocation.project_dir is not None:
        pipelines_root = invocation.project_dir / "pipelines"
    if pipelines_root is None or not pipelines_root.is_dir():
        return False
    for config_path in pipelines_root.glob("*/pipeline.toml"):
        try:
            values: dict[str, object] = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if values.get("mode") == PipelineMode.VIRTUAL:
            return True
    return False


def _is_virtual_environment_only(*, args: argparse.Namespace) -> bool:
    command: CliCommand = CliCommand(args.command)
    return command in VIRTUAL_ENVIRONMENT_ONLY_COMMANDS


def _command_display(*, args: argparse.Namespace) -> str:
    if args.command == CliCommand.DEPLOYMENT:
        return f"deployment {args.deployment_command}"
    if args.command == CliCommand.REPAIR:
        return "repair active-view"
    return str(args.command)
