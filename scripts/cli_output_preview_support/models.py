"""Preview request models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewRequest:
    """One preview rendering request as the script received it."""

    database: str
    json_output: bool
    verbose: bool
