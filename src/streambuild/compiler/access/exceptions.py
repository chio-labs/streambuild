"""Access-policy compilation failures."""

from streambuild.diagnostics.models import SourceLocation


class AccessPolicyError(ValueError):
    """Authored access policy is unsafe or invalid."""

    def __init__(self, message: str, *, location: SourceLocation) -> None:
        super().__init__(message)
        self.location = location
