"""Render the message shown when no deployment candidates exist."""

from __future__ import annotations

from streambuild.cli.shared.main._cli_style import cli_style


def render_no_deployment_candidates_message(*, command_name: str, database: str) -> str:
    return "\n".join(
        [
            cli_style().title(f"No staged deployment candidates are available for {command_name}"),
            cli_style().label_value(label="Database", value=database),
        ]
    )
