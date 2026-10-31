"""Entry point for MODEL(...) header audit instance construction."""

from __future__ import annotations

from sqltide.compiler.audit_discovery._helpers.generic import (
    build_model_header_generic_sql_audit_instances,
)
from sqltide.compiler.audit_discovery.models import LoadedGenericSqlAuditInstance
from sqltide.compiler.discovery.models import TransformStep, ViewStep


def build_model_audit_instances(
    *,
    models: tuple[TransformStep | ViewStep, ...],
) -> tuple[LoadedGenericSqlAuditInstance, ...]:
    """Build generic audit instances declared in MODEL(...) headers."""

    return build_model_header_generic_sql_audit_instances(models=models)
