"""Parse compact authored durations into typed seconds."""

import re

from streambuild.compiler.discovery.constants import DURATION_PATTERN, SECONDS_BY_DURATION_UNIT
from streambuild.compiler.discovery.exceptions import DurationParseError


def parse_duration_seconds(*, value: object, field_path: str, allow_zero: bool) -> int:
    """Parse one `<int><s|m|h|d>` duration with explicit zero semantics."""

    if not isinstance(value, str):
        raise DurationParseError(
            f"{field_path} must be a duration such as '30s', '5m', '2h', or '1d'"
        )
    match: re.Match[str] | None = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise DurationParseError(
            f"{field_path} must be a duration such as '30s', '5m', '2h', or '1d'"
        )
    seconds: int = int(match.group(1)) * SECONDS_BY_DURATION_UNIT[match.group(2)]
    if seconds == 0 and not allow_zero:
        raise DurationParseError(f"{field_path} must be greater than zero")
    return seconds
