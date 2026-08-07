"""Build deterministic storage identity for one compiled model."""

from __future__ import annotations

from streambuild.compiler.compile.models import CompiledModel, CompiledTableModel


def build_model_storage_identity(model: CompiledModel) -> dict[str, object] | None:
    """Return the MODEL header storage spec that participates in baseline identity."""

    if not isinstance(model, CompiledTableModel):
        return None
    return {
        "engine": model.transform.engine,
        "order_by": list(model.transform.order_by),
        "partition_by": model.transform.partition_by,
        "ttl": model.transform.ttl,
        "settings": None if model.transform.settings is None else dict(model.transform.settings),
    }
