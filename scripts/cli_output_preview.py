"""Preview representative CLI output shapes without running the stack."""

from __future__ import annotations

import argparse

from scripts.cli_output_preview_support.constants import (
    ALL_SCENARIOS_CHOICE,
    PREVIEW_SCENARIO_NAMES,
)
from scripts.cli_output_preview_support.main.print_cli_output_preview import (
    print_cli_output_preview,
)


def _build_parser() -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Preview representative CLI output",
    )
    parser.add_argument("scenario", choices=(*PREVIEW_SCENARIO_NAMES, ALL_SCENARIOS_CHOICE))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def _parse_args() -> argparse.Namespace:
    return _build_parser().parse_args()


def main() -> int:
    args: argparse.Namespace = _parse_args()
    return print_cli_output_preview(
        scenario=args.scenario,
        json_output=args.json,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    raise SystemExit(main())
