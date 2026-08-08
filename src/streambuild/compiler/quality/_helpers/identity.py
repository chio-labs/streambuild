"""Canonical quality identity hashing."""

import json
from hashlib import sha256

from streambuild.compiler.quality.models import QualityNodeIdentity
from streambuild.compiler.quality.types import QualityNodeKind


def quality_node_name(*, name: str | None, file_stem: str) -> str:
    return name or file_stem


def build_identity(
    *,
    node_kind: QualityNodeKind,
    node_name: str,
    binding_payload: dict[str, object],
    definition: dict[str, object],
    execution: dict[str, object],
) -> QualityNodeIdentity:
    return QualityNodeIdentity(
        node_kind=node_kind,
        node_name=node_name,
        binding_key=_fingerprint(binding_payload),
        definition_fingerprint=_fingerprint(definition),
        execution_fingerprint=_fingerprint(execution),
    )


def _fingerprint(payload: dict[str, object]) -> str:
    canonical_payload: str = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(canonical_payload.encode()).hexdigest()
