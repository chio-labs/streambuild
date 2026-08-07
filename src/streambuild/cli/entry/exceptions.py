"""CLI-specific expected exception types."""


class CliUserError(Exception):
    """Expected CLI-facing error that should be rendered without a traceback."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint: str | None = hint
