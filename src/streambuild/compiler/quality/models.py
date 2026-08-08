"""Compiler-neutral quality identity models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityNodeIdentity:
    """Stable logical, definition, and executable identity for one quality node."""

    node_kind: str
    node_name: str
    binding_key: str
    definition_fingerprint: str
    execution_fingerprint: str
