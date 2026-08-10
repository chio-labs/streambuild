"""Build command policy exceptions."""

from streambuild.cli.entry.exceptions import CliUserError


class BuildPipelineLimitError(CliUserError):
    """The final build closure exceeds its committed target limit."""
