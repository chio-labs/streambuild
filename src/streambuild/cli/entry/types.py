"""CLI entry runtime domain types."""

from enum import StrEnum


class CliCommand(StrEnum):
    """One top-level `stb` subcommand as argparse reports it."""

    DISCOVER = "discover"
    COMPILE = "compile"
    TEST = "test"
    PLAN = "plan"
    BACKFILL = "backfill"
    BUILD = "build"
    AUDIT = "audit"
    PUBLISH = "publish"
    RECONCILE = "reconcile"
    JANITOR = "janitor"
    DOCTOR = "doctor"
    REPAIR = "repair"


class CliSubcommand(StrEnum):
    """One nested `stb <command> <subcommand>` selector."""

    BACKFILL = "backfill"
    ACTIVE_VIEW = "active-view"
