"""Fingerprint one quality node definition for stale-result detection."""

from hashlib import sha256


def build_definition_fingerprint(*, definition: str, severity: str | None) -> str:
    """Return the stable fingerprint recorded with, and compared against, results."""

    fingerprint_definition: str = (
        definition if severity is None else f"{definition}\nseverity={severity}"
    )
    return sha256(fingerprint_definition.encode()).hexdigest()
