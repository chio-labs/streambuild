"""Format an optional count for human output."""

from streambuild.cli.shared.constants import NOT_AVAILABLE


def format_count(value: int | None) -> str:
    """Render a count, or n/a when it is unknown."""

    if value is None:
        return NOT_AVAILABLE
    return str(value)
