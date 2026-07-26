"""Build the CLI style facade for the current terminal."""

from __future__ import annotations

import os
import sys

from streambuild.cli.shared.classes.cli_style import CliStyle
from streambuild.cli.shared.constants import TRUTHY_ENV_VALUES


def cli_style() -> CliStyle:
    """Return a style facade reflecting whether colour is currently enabled.

    Colour is resolved per call rather than cached so environment changes and
    redirected output are honoured.
    """

    return CliStyle(use_color=_color_enabled())


def _color_enabled() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if (
        os.getenv("CLICOLOR_FORCE") in TRUTHY_ENV_VALUES
        or os.getenv("FORCE_COLOR") in TRUTHY_ENV_VALUES
    ):
        return True
    return sys.stdout.isatty()
