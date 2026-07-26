"""Format a min/max pair for human output."""

from streambuild.cli.shared.constants import NOT_AVAILABLE


def format_range(*, min_value: str | None, max_value: str | None) -> str:
    """Render a bounded range, or n/a when both bounds are unknown."""

    if min_value is None and max_value is None:
        return NOT_AVAILABLE
    return f"{min_value or NOT_AVAILABLE} .. {max_value or NOT_AVAILABLE}"
