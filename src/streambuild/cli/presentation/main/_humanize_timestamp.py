"""Render a warehouse timestamp for human output."""

from streambuild.cli.presentation.constants import UTC_SUFFIX


def humanize_timestamp(value: str) -> str:
    """Normalise a warehouse timestamp to an ISO-8601 UTC string."""

    normalized: str = value.replace(" ", "T")
    if normalized.endswith(UTC_SUFFIX):
        return normalized
    return f"{normalized}{UTC_SUFFIX}"
