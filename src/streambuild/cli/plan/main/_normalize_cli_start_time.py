"""Normalize a CLI-supplied start time to a canonical form."""

from __future__ import annotations

from datetime import datetime

from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.constants import (
    ACCEPTED_START_TIME_FORMATS,
    CLICKHOUSE_TIMESTAMP_FORMAT,
    DATE_ONLY_START_TIME_FORMAT,
    START_OF_DAY_CLICKHOUSE_FORMAT,
)


def normalize_cli_start_time(raw_value: str) -> str:
    """Normalize a CLI start time into a ClickHouse millisecond timestamp."""

    date_format: str
    for date_format in ACCEPTED_START_TIME_FORMATS:
        try:
            parsed_value: datetime = datetime.strptime(raw_value, date_format)
        except ValueError:
            continue
        if date_format == DATE_ONLY_START_TIME_FORMAT:
            return parsed_value.strftime(START_OF_DAY_CLICKHOUSE_FORMAT)
        return parsed_value.strftime(CLICKHOUSE_TIMESTAMP_FORMAT)[:-3]
    raise CliUserError(
        "--start-time must be YYYY-MM-DD or a UTC timestamp like YYYY-MM-DDTHH:MM:SS[.sss][Z]"
    )
