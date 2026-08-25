"""Compare compiled direct models with their last applied fingerprints."""

from __future__ import annotations

import json
from hashlib import sha256

from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
)
from streambuild.compiler.compile.models import CompiledModel, CompiledTableModel
from streambuild.compiler.pipeline.models import RealizedProject

_STORAGE_IDENTITY_KEY: str = "storage"


def _direct_model_drift_reasons(
    *,
    model: CompiledModel,
    realized_project: RealizedProject,
    baseline: AdapterDirectFingerprintRecord | None,
) -> tuple[str, ...]:
    """Return direct fingerprint differences shared by native planning and the UI."""

    if baseline is None:
        return ()
    reasons: list[str] = []
    if sha256(model.query.encode()).hexdigest() != baseline.definition_hash:
        reasons.append("query")
    baseline_identity: dict[str, object] | None = _baseline_identity(baseline=baseline)
    desired_identity: dict[str, object] = _build_direct_model_identity(
        model=model,
        realized_project=realized_project,
    )
    if (
        isinstance(model, CompiledTableModel)
        and _identity_value(identity=baseline_identity, key=_STORAGE_IDENTITY_KEY)
        != desired_identity[_STORAGE_IDENTITY_KEY]
    ):
        reasons.append("storage")
    if _without_storage(baseline_identity) != _without_storage(desired_identity):
        reasons.append("identity")
    return tuple(reasons)


def _build_direct_model_identity(
    *, model: CompiledModel, realized_project: RealizedProject
) -> dict[str, object]:
    """Return the complete realized identity persisted for changed selection."""

    resources: list[dict[str, object]] = []
    for resource in realized_project.resources_by_logical_key.get(model.key, ()):
        if isinstance(resource, AdapterTable):
            resources.append(
                {
                    "kind": "table",
                    "name": resource.name,
                    "columns": [
                        {
                            "name": column.name,
                            "type": column.type,
                            "default_expression": column.default_expression,
                        }
                        for column in resource.columns
                    ],
                    "engine": resource.engine,
                    "order_by": list(resource.order_by),
                    "partition_by": resource.partition_by,
                    "ttl": resource.ttl,
                    "settings": dict(resource.settings),
                }
            )
        elif isinstance(resource, AdapterMaterializedView):
            resources.append(
                {
                    "kind": "materialized_view",
                    "name": resource.name,
                    "source_relation_name": resource.source_relation_name,
                    "target_relation_name": resource.target_relation_name,
                    "query": resource.query,
                    "database_template": resource.database_template,
                    "refresh": resource.refresh,
                    "append": resource.append,
                }
            )
        elif isinstance(resource, AdapterView):
            resources.append(
                {
                    "kind": "view",
                    "name": resource.name,
                    "query": resource.query,
                    "database_template": resource.database_template,
                }
            )
    return {
        "pipeline": model.pipeline_name,
        "kind": str(model.kind),
        "relations": [resource["name"] for resource in resources],
        "storage": build_model_storage_identity(model),
        "resources": resources,
    }


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
    """Build and compare complete realized direct-model fingerprints."""

    @staticmethod
    def identity(*, model: CompiledModel, realized_project: RealizedProject) -> dict[str, object]:
        return _build_direct_model_identity(model=model, realized_project=realized_project)

    @staticmethod
    def drift_reasons(
        *,
        model: CompiledModel,
        realized_project: RealizedProject,
        baseline: AdapterDirectFingerprintRecord | None,
    ) -> tuple[str, ...]:
        return _direct_model_drift_reasons(
            model=model,
            realized_project=realized_project,
            baseline=baseline,
        )
