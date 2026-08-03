"""CLI entry constants."""

from collections.abc import Mapping

from streambuild.cli.entry.types import CliCommand, CliSubcommand

ACTIVE_VIEW_SUBCOMMAND: str = CliSubcommand.ACTIVE_VIEW

COMMANDS_REQUIRING_PIPELINES_ROOT: frozenset[CliCommand] = frozenset(
    {
        CliCommand.DEV,
        CliCommand.DISCOVER,
        CliCommand.COMPILE,
        CliCommand.TEST,
        CliCommand.PLAN,
        CliCommand.BUILD,
        CliCommand.RECONCILE,
        CliCommand.AUDIT,
    }
)
COMMANDS_WITHOUT_ADAPTER_CONNECTION: frozenset[CliCommand] = frozenset(
    {CliCommand.DISCOVER, CliCommand.COMPILE}
)
DIRECT_ONLY_COMMANDS: frozenset[CliCommand] = frozenset()
VIRTUAL_ENVIRONMENT_ONLY_COMMANDS: frozenset[CliCommand] = frozenset(
    {
        CliCommand.PUBLISH,
        CliCommand.RECONCILE,
        CliCommand.JANITOR,
        CliCommand.DOCTOR,
        CliCommand.REPAIR,
    }
)

DISPLAY_NAME_BY_COMMAND: Mapping[CliCommand, str] = {
    CliCommand.AUDIT: "audit",
    CliCommand.REPAIR: "repair active-view",
}

METADATA_TABLE_NAME_PREFIX: str = "streambuild_"
AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({"y", "yes"})
