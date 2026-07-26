"""Preview representative CLI output shapes without running the stack."""

from __future__ import annotations

import argparse

from scripts.cli_output_preview_support.constants import (
    ALL_SCENARIOS_CHOICE,
    PREVIEW_SCENARIO_NAMES,
)
from scripts.cli_output_preview_support.main.render_cli_output_preview import (
    render_cli_output_preview,
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
    requested: tuple[str, ...] = (
        PREVIEW_SCENARIO_NAMES if args.scenario == ALL_SCENARIOS_CHOICE else (args.scenario,)
    )
    scenario_name: str
    for index, scenario_name in enumerate(requested):
        if index > 0:
            print("\n---\n")
        print(
            render_cli_output_preview(
                scenario_name=scenario_name,
                json_output=args.json,
                verbose=args.verbose,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
