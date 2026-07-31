"""Audit selection helpers for the audit backfill command."""

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import CompiledModel, CompiledPipeline
from streambuild.executor.audit_backfill.models import (
    LoadedAuditDeployment,
)


def selected_backfill_sql_audits(
    *,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    loaded_audits: tuple[LoadedSqlAudit, ...],
    staged_logical_table_names: frozenset[str],
) -> tuple[LoadedSqlAudit, ...]:
    selected_audits: list[LoadedSqlAudit] = []
    relation_name_by_model_name: dict[str, str] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        compiled_model: CompiledModel
        for compiled_model in compiled_pipeline.models:
            relation_name_by_model_name[compiled_model.key.name] = compiled_model.relation_name
    loaded_audit: LoadedSqlAudit
    for loaded_audit in loaded_audits:
        model_name: str
        for model_name in loaded_audit.referenced_model_names:
            if relation_name_by_model_name[model_name] in staged_logical_table_names:
                selected_audits.append(loaded_audit)
                break
    return tuple(selected_audits)


def backfill_audit_resolver(
    *,
    database: str,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    loaded_deployment: LoadedAuditDeployment,
) -> dict[str, str]:
    staged_name_by_logical_name: dict[str, str] = {
        logical_key.name: physical_name
        for logical_key, physical_name in loaded_deployment.prepared_object_mappings
    }
    resolver: dict[str, str] = {}
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled_pipelines:
        compiled_model: CompiledModel
        for compiled_model in compiled_pipeline.models:
            resolved_table_name: str = resolved_audit_table_name(
                relation_name=compiled_model.relation_name,
                staged_name_by_logical_name=staged_name_by_logical_name,
            )
            resolver[compiled_model.key.name] = f"{database}.{resolved_table_name}"
    return resolver


def resolved_audit_table_name(
    *,
    relation_name: str,
    staged_name_by_logical_name: dict[str, str],
) -> str:
    return staged_name_by_logical_name.get(relation_name, relation_name)
