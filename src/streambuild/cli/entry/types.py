"""CLI entry runtime domain types."""

from enum import StrEnum


class CliCommand(StrEnum):
    """One top-level `stb` subcommand as argparse reports it."""

    DISCOVER = "discover"
    DEV = "dev"
    COMPILE = "compile"
    TEST = "test"
    PLAN = "plan"
    BUILD = "build"
    AUDIT = "audit"
    PUBLISH = "publish"
    RECONCILE = "reconcile"
    JANITOR = "janitor"
    DOCTOR = "doctor"
    REPAIR = "repair"


class CliSubcommand(StrEnum):
    """One nested `stb <command> <subcommand>` selector."""

    DEPLOYMENT = "deployment"
    ACTIVE_VIEW = "active-view"
