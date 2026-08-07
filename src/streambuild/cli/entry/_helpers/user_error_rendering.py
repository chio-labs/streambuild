"""Render expected operator-correctable CLI errors."""

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.presentation.classes.cli_style import CliStyle
from streambuild.cli.presentation.main._cli_style import cli_style


def render_cli_user_error(error: CliUserError) -> str:
    """Return a concise styled error with an optional corrective hint."""

    style: CliStyle = cli_style()
    lines: list[str] = [style.outcome(text="Error", passed=False), str(error)]
    if error.hint is not None:
        lines.extend(("", f"{style.warning('Hint')}: {error.hint}"))
    return "\n".join(lines)
