"""Format a ratio as a percentage for human output."""


def format_percentage(value: float) -> str:
    """Render a 0..1 ratio as a one-decimal percentage."""

    return f"{value * 100:.1f}%"
