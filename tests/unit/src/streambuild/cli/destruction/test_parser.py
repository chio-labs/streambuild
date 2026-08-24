import argparse

import pytest

from streambuild.cli.entry._helpers.parser import build_cli_parser
from tests.unit.src.streambuild.cli.destruction._test_types import (
    DestructionParserTestCase,
    DestructionRejectedOptionTestCase,
)

_DESTROY_REQUIRED_ARGUMENTS: tuple[str, ...] = ("--select", "pipeline:alpha")
_RESET_REQUIRED_ARGUMENTS: tuple[str, ...] = ()


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionParserTestCase(
            description="destroy requires target and explicit pipeline selectors",
            argv=(
                "destroy",
                "--target",
                "uat",
                "--select",
                "pipeline:alpha",
                "pipeline:beta",
                "--control-store-url",
                "sqlite:////tmp/destruction-control.db",
            ),
            expected_command="destroy",
            expected_target="uat",
            expected_selectors=("pipeline:alpha", "pipeline:beta"),
            expected_control_store_url="sqlite:////tmp/destruction-control.db",
        ),
        DestructionParserTestCase(
            description="reset target requires the named target without selection",
            argv=("reset-target", "--target", "production"),
            expected_command="reset-target",
            expected_target="production",
            expected_selectors=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_destruction_arguments_when_parsing_then_command_contract_is_explicit(
    test_case: DestructionParserTestCase,
) -> None:
    # Given: A destructive command with its mandatory scope.
    parser: argparse.ArgumentParser = build_cli_parser()

    # When: The arguments are parsed.
    parsed: argparse.Namespace = parser.parse_args(test_case.argv)

    # Then: Only the explicit target and pipeline selection are represented.
    assert parsed.command == test_case.expected_command
    assert parsed.target == test_case.expected_target
    assert tuple(getattr(parsed, "select", ())) == test_case.expected_selectors
    assert parsed.control_store_url == test_case.expected_control_store_url


@pytest.mark.parametrize(
    "test_case",
    [
        DestructionRejectedOptionTestCase(
            "destroy yes is unavailable", "destroy", _DESTROY_REQUIRED_ARGUMENTS, "--yes", 2
        ),
        DestructionRejectedOptionTestCase(
            "destroy force is unavailable", "destroy", _DESTROY_REQUIRED_ARGUMENTS, "--force", 2
        ),
        DestructionRejectedOptionTestCase(
            "destroy auto approve is unavailable",
            "destroy",
            _DESTROY_REQUIRED_ARGUMENTS,
            "--auto-approve",
            2,
        ),
        DestructionRejectedOptionTestCase(
            "destroy confirm is unavailable", "destroy", _DESTROY_REQUIRED_ARGUMENTS, "--confirm", 2
        ),
        DestructionRejectedOptionTestCase(
            "destroy apply is unavailable", "destroy", _DESTROY_REQUIRED_ARGUMENTS, "--apply", 2
        ),
        DestructionRejectedOptionTestCase(
            "destroy no confirm is unavailable",
            "destroy",
            _DESTROY_REQUIRED_ARGUMENTS,
            "--no-confirm",
            2,
        ),
        DestructionRejectedOptionTestCase(
            "destroy json is unavailable", "destroy", _DESTROY_REQUIRED_ARGUMENTS, "--json", 2
        ),
        DestructionRejectedOptionTestCase(
            "reset yes is unavailable", "reset-target", _RESET_REQUIRED_ARGUMENTS, "--yes", 2
        ),
        DestructionRejectedOptionTestCase(
            "reset force is unavailable", "reset-target", _RESET_REQUIRED_ARGUMENTS, "--force", 2
        ),
        DestructionRejectedOptionTestCase(
            "reset auto approve is unavailable",
            "reset-target",
            _RESET_REQUIRED_ARGUMENTS,
            "--auto-approve",
            2,
        ),
        DestructionRejectedOptionTestCase(
            "reset confirm is unavailable",
            "reset-target",
            _RESET_REQUIRED_ARGUMENTS,
            "--confirm",
            2,
        ),
        DestructionRejectedOptionTestCase(
            "reset apply is unavailable", "reset-target", _RESET_REQUIRED_ARGUMENTS, "--apply", 2
        ),
        DestructionRejectedOptionTestCase(
            "reset no confirm is unavailable",
            "reset-target",
            _RESET_REQUIRED_ARGUMENTS,
            "--no-confirm",
            2,
        ),
        DestructionRejectedOptionTestCase(
            "reset json is unavailable", "reset-target", _RESET_REQUIRED_ARGUMENTS, "--json", 2
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bypass_option_when_parsing_destroy_then_parser_rejects_it(
    test_case: DestructionRejectedOptionTestCase,
) -> None:
    # Given: A complete destroy command plus a forbidden bypass option.
    argv: tuple[str, ...] = (
        test_case.command,
        "--target",
        "uat",
        *test_case.required_arguments,
        test_case.option,
    )

    # When: The command is parsed, then the unsupported option is rejected.
    with pytest.raises(SystemExit) as raised:
        build_cli_parser().parse_args(argv)

    # Then: argparse reports command-line misuse.
    assert raised.value.code == test_case.expected_exit_code
