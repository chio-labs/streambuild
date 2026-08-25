"""Compare compiled direct models with their last applied fingerprints."""

from __future__ import annotations

import json
from hashlib import sha256

from streambuild.adapter.models import AdapterDirectFingerprintRecord
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
)
from streambuild.compiler.compile.models import CompiledModel, CompiledTableModel

_STORAGE_IDENTITY_KEY: str = "storage"


def _direct_model_drift_reasons(
    *,
    model: CompiledModel,
    baseline: AdapterDirectFingerprintRecord | None,
) -> tuple[str, ...]:
    """Return direct fingerprint differences shared by native planning and the UI."""

    if baseline is None:
        return ("missing",)
    reasons: list[str] = []
    if _query_hash(model.query) != baseline.definition_hash:
        reasons.append("query")
    baseline_identity: dict[str, object] | None = _baseline_identity(baseline=baseline)
    desired_identity: dict[str, object] = _build_direct_model_identity(model=model)
    if (
        isinstance(model, CompiledTableModel)
        and _identity_value(identity=baseline_identity, key=_STORAGE_IDENTITY_KEY)
        != desired_identity[_STORAGE_IDENTITY_KEY]
    ):
        reasons.append("storage")
    if _without_storage(baseline_identity) != _without_storage(desired_identity):
        reasons.append("identity")
    return tuple(reasons)


def _build_direct_model_identity(*, model: CompiledModel) -> dict[str, object]:
    """Return the allowlisted semantic identity persisted for changed selection."""

    return {
        "identity_version": 1,
        "model_name": model.key.name,
        "kind": str(model.kind),
        "relation_name": model.relation_name,
        "output_columns": [
            {"name": column.name, "type": column.type} for column in model.output_columns
        ],
        "storage": build_model_storage_identity(model),
    }


def _query_hash(query_sql: str) -> str:
    return sha256(query_sql.encode()).hexdigest()


def _baseline_identity(*, baseline: AdapterDirectFingerprintRecord) -> dict[str, object] | None:
    try:
        metadata: object = json.loads(baseline.identity_metadata)
    except (TypeError, ValueError):
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata


def _identity_value(*, identity: dict[str, object] | None, key: str) -> object:
    return None if identity is None else identity.get(key)


def _without_storage(identity: dict[str, object] | None) -> dict[str, object] | None:
    if identity is None:
        return None
    return {key: value for key, value in identity.items() if key != _STORAGE_IDENTITY_KEY}


class DirectModelFingerprint:
    """Build and compare canonical semantic direct-model fingerprints."""

    @staticmethod
    def identity(*, model: CompiledModel) -> dict[str, object]:
        return _build_direct_model_identity(model=model)

    @staticmethod
    def query_hash(query_sql: str) -> str:
        return _query_hash(query_sql)

    @staticmethod
    def drift_reasons(
        *,
        model: CompiledModel,
        baseline: AdapterDirectFingerprintRecord | None,
    ) -> tuple[str, ...]:
        return _direct_model_drift_reasons(
            model=model,
            baseline=baseline,
        )
