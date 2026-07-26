"""Format a boolean for human output."""


def format_bool(value: bool) -> str:
    """Render a boolean as yes or no."""

    return "yes" if value else "no"
