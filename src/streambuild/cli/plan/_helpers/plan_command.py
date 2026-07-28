"""Route one `stb plan` invocation from the single effective project mode."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan._helpers.standard_command import execute_standard_plan
from streambuild.cli.plan._helpers.virtual_environment_command import (
    execute_virtual_environment_plan,
)
from streambuild.cli.plan.main._normalize_cli_start_time import normalize_cli_start_time
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.compiler.pipeline.models import CompileAnalysis

_VIRTUAL_ENVIRONMENT_ONLY_FLAGS: tuple[tuple[str, str], ...] = (
    ("--full-refresh", "full_refresh"),
    ("--start-time", "start_time"),
)


def execute_plan_command(
    *,
    analysis: CompileAnalysis,
    options: PlanCommandOptions,
    client: AdapterConnection,
) -> str:
    """Plan through the mode already resolved from project and local configuration."""

    if analysis.compile_inputs.virtual_environments:
        return execute_virtual_environment_plan(
            analysis=analysis,
            options=options,
            client=client,
            normalized_utc_start_time=_normalized_utc_start_time(options=options),
        )
    _reject_virtual_environment_only_flags(options=options)
    return execute_standard_plan(analysis=analysis, options=options, client=client)


def validate_plan_flags(*, options: PlanCommandOptions) -> None:
    """Reject flag combinations that are invalid regardless of effective mode."""

    if options.full_refresh and options.start_time is not None:
        raise CliUserError("--full-refresh cannot be combined with --start-time")
    if (options.full_refresh or options.start_time is not None) and not options.selectors:
        required_flag: str = "--full-refresh" if options.full_refresh else "--start-time"
        raise CliUserError(f"{required_flag} requires at least one --select")


def _normalized_utc_start_time(*, options: PlanCommandOptions) -> str | None:
    if options.start_time is None:
        return None
    return normalize_cli_start_time(options.start_time)


def _reject_virtual_environment_only_flags(*, options: PlanCommandOptions) -> None:
    flag_name: str
    attribute_name: str
    for flag_name, attribute_name in _VIRTUAL_ENVIRONMENT_ONLY_FLAGS:
        if getattr(options, attribute_name):
            raise CliUserError(
                f"{flag_name} is a virtual-environment replay control and is not available in "
                "standard mode. Enable settings.virtual_environments to use it."
            )
