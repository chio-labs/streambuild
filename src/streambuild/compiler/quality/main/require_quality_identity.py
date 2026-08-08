"""Require compiled identity before quality persistence."""

from streambuild.compiler.quality.exceptions import QualityIdentityError
from streambuild.compiler.quality.models import QualityNodeIdentity


def require_quality_identity(identity: QualityNodeIdentity | None) -> QualityNodeIdentity:
    """Return a compiled identity or fail before writing incomplete metadata."""

    if identity is None:
        raise QualityIdentityError("Quality node does not have a compiled identity")
    return identity
