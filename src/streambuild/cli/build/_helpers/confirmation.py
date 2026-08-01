"""Shared confirmation vocabulary for direct and virtual builds."""

from streambuild.cli.build.models import BuildCommandOptions
from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES


def confirm_build(*, options: BuildCommandOptions, plan_text: str) -> bool:
    """Render the connected plan and apply the common build confirmation policy."""

    if not options.json_output:
        print(plan_text)
    if options.auto_approve:
        return True
    return input("Proceed with build? [y/N] ").strip().lower() in AFFIRMATIVE_RESPONSES
