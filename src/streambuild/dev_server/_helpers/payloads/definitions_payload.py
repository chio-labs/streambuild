"""Serialize one CompileAnalysis into the /api/definitions payload."""

from __future__ import annotations

from pathlib import Path

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.adapters.clickhouse.main.database_scoped_consumer_group import (
    database_scoped_consumer_group,
)
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledSource,
    CompiledTableModel,
    CompiledViewModel,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.models import (
    EffectiveProjectConfiguration,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedProject,
    ModelColumnSpec,
    PipelineProtection,
    PostgresRefreshSourceStep,
    ReplayBoundary,
    SourceFreshnessPolicy,
)
from streambuild.compiler.discovery.types import ReplayAnchorMode, SourceKind
from streambuild.compiler.graph.models import DependencyEdge
from streambuild.compiler.graph.types import DependencyEdgeType
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.quality.models import QualityNodeIdentity
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.dev_server._helpers.server.redaction import (
    redacted_broker_list,
    redacted_source_settings,
)
from streambuild.dev_server.types import ReplayAnchorReason

_CONNECTION_SECRET_KEYS: frozenset[str] = frozenset({"password"})
_FALLBACK_RENDER_DATABASE: str = "default"


def build_definitions_payload(
    *,
    analysis: CompileAnalysis,
    version_key: str,
) -> dict[str, object]:
    """Build the complete static definitions payload for one held compile."""

    database: str = _render_database(analysis)
    return {
        "versionKey": version_key,
        "project": _project_payload(analysis),
        "sources": [
            _source_payload(analysis=analysis, source=source)
            for source in analysis.compiled_project.sources
        ],
        "pipelines": [
            _pipeline_payload(analysis=analysis, pipeline=pipeline)
            for pipeline in analysis.compiled_project.pipelines
        ],
        "models": [
            _model_payload(analysis=analysis, model=model, database=database)
            for model in analysis.compiled_project.models
        ],
        "audits": [_audit_payload(audit) for audit in analysis.compiled_project.audits],
        "tests": [_test_payload(test_case) for test_case in analysis.compiled_project.test_cases],
        "macros": _macro_payloads(analysis),
    }


def _render_database(analysis: CompileAnalysis) -> str:
    configured: str | None = analysis.compile_inputs.effective_target.default_database
    return configured or _FALLBACK_RENDER_DATABASE


def _project_payload(analysis: CompileAnalysis) -> dict[str, object]:
    loaded: LoadedProject | None = analysis.discovered_inputs.loaded_project
    effective: EffectiveProjectConfiguration | None = (
        None if loaded is None else loaded.effective_configuration
    )
    if effective is None:
        return {
            "name": None,
            "adapter": None,
            "target": None,
            "database": None,
            "vars": {},
            "naming": None,
            "defaults": None,
            "connection": {},
            "auditScheduler": {"enabled": False},
        }
    return {
        "name": effective.name,
        "adapter": effective.adapter,
        "target": effective.target_name,
        "database": effective.database,
        "vars": dict(effective.variables),
        "naming": {
            "tablePrefix": effective.naming.table_prefix,
            "viewPrefix": effective.naming.view_prefix,
        },
        "defaults": {
            "managedSourceTtl": effective.defaults.managed_source_ttl,
            "modelTtl": effective.defaults.model_ttl,
            "kafkaBrokerList": (
                None
                if effective.defaults.kafka_broker_list is None
                else redacted_broker_list(effective.defaults.kafka_broker_list)
            ),
            "freshness": _freshness_payload(effective.defaults.freshness),
            "audits": {
                "severity": effective.defaults.audits.severity,
                "cadenceSeconds": effective.defaults.audits.cadence_seconds,
                "warmupSeconds": effective.defaults.audits.warmup_seconds,
            },
        },
        "connection": {
            key: value
            for key, value in effective.connection.values
            if key not in _CONNECTION_SECRET_KEYS
        },
        "auditScheduler": {"enabled": effective.audit_scheduler.enabled},
    }


def _freshness_payload(policy: SourceFreshnessPolicy | None) -> dict[str, object] | None:
    if policy is None:
        return None
    return {"warnAfter": policy.warn_after, "errorAfter": policy.error_after}


def _source_payload(*, analysis: CompileAnalysis, source: CompiledSource) -> dict[str, object]:
    step: KafkaLandingStep | ExternalTableSourceStep | PostgresRefreshSourceStep = source.source
    relation_name: str = analysis.realized_project.relation_name_by_logical_key[source.key]
    database: str = _render_database(analysis)
    managed: list[dict[str, object]] = []
    kafka: dict[str, object] | None = None
    resource: object
    for resource in analysis.realized_project.resources_by_logical_key.get(source.key, ()):
        managed.append(
            _managed_relation_payload(analysis=analysis, resource=resource, database=database)
        )
        if isinstance(resource, AdapterManagedSource):
            kafka = {
                "brokerList": redacted_broker_list(resource.broker_list),
                "topic": resource.topic,
                "consumerGroup": database_scoped_consumer_group(
                    consumer_group=resource.consumer_group,
                    database=database,
                ),
                "format": resource.format,
                "settings": redacted_source_settings(dict(resource.settings) or None),
            }
    boundary: ReplayBoundary | None = (
        None if isinstance(step, PostgresRefreshSourceStep) else step.replay_boundary
    )
    return {
        "name": source.key.name,
        "nameOrigin": {
            "kind": step.name_origin,
            "macro": getattr(step, "naming_macro", None),
            "macroFingerprint": getattr(step, "naming_macro_fingerprint", None),
        },
        "kind": (
            SourceKind.KAFKA.value
            if isinstance(step, KafkaLandingStep)
            else SourceKind.POSTGRES.value
            if isinstance(step, PostgresRefreshSourceStep)
            else SourceKind.STREAM_TABLE.value
        ),
        "boundaryMode": str(source.effective_replay_lineage_mode),
        "relationName": relation_name,
        "managedRelations": managed,
        "ttl": step.kafka.ttl if isinstance(step, KafkaLandingStep) else None,
        "kafka": kafka,
        "columnMapping": _boundary_columns_payload(boundary),
        "freshness": _freshness_payload(step.freshness),
        "refresh": step.refresh if isinstance(step, PostgresRefreshSourceStep) else None,
    }


def _managed_relation_payload(
    *, analysis: CompileAnalysis, resource: object, database: str
) -> dict[str, object]:
    kind_by_type: dict[type, str] = {
        AdapterManagedSource: "kafka_engine",
        AdapterTable: "landing_table",
        AdapterMaterializedView: "landing_mv",
    }
    return {
        "kind": kind_by_type.get(type(resource), "unknown"),
        "name": getattr(resource, "name", ""),
        "ddl": _managed_relation_ddl(analysis=analysis, resource=resource, database=database),
    }


def _managed_relation_ddl(
    *, analysis: CompileAnalysis, resource: object, database: str
) -> str | None:
    if not isinstance(resource, AdapterManagedSource | AdapterTable | AdapterMaterializedView):
        return None
    return analysis.adapter_profile.render_resource(resource=resource, database=database)


def _boundary_columns_payload(boundary: object) -> dict[str, str] | None:
    columns: object = getattr(boundary, "columns", None)
    if columns is None:
        return None
    mapping: dict[str, str] = {}
    role: str
    for role in ("partition", "offset", "timestamp", "landed_at", "cursor"):
        value: object = getattr(columns, role, None)
        if isinstance(value, str):
            mapping[role] = value
    return mapping or None


def _pipeline_payload(
    *, analysis: CompileAnalysis, pipeline: CompiledPipeline
) -> dict[str, object]:
    protection: PipelineProtection | None = pipeline.pipeline.protection
    return {
        "name": pipeline.pipeline.name,
        "mode": str(pipeline.pipeline.mode),
        "sourceName": None if pipeline.source is None else pipeline.source.key.name,
        "boundaryMode": str(pipeline.effective_replay_lineage_mode),
        "models": [model.key.name for model in pipeline.models],
        "directory": f"pipelines/{pipeline.pipeline.name}",
        "naming": {
            "tablePrefix": pipeline.pipeline.naming.table_prefix,
            "viewPrefix": pipeline.pipeline.naming.view_prefix,
        },
        "protection": (
            None
            if protection is None
            else {
                "warning": protection.warning,
                "confirmation": protection.confirmation,
            }
        ),
        "auditDefaults": {
            "severity": pipeline.pipeline.audit_defaults.severity,
            "cadenceSeconds": pipeline.pipeline.audit_defaults.cadence_seconds,
            "warmupSeconds": pipeline.pipeline.audit_defaults.warmup_seconds,
        },
    }


def _model_payload(
    *, analysis: CompileAnalysis, model: CompiledModel, database: str
) -> dict[str, object]:
    edges: tuple[DependencyEdge, ...] = analysis.graph.upstream_edges_by_key.get(model.key, ())
    refs: list[dict[str, object]] = [
        {
            "name": edge.upstream_key.name,
            "type": str(edge.edge_type),
            "isSource": edge.upstream_key.resource_type == LogicalResourceType.SOURCE,
        }
        for edge in edges
    ]
    driving: str | None = None
    edge: DependencyEdge
    for edge in edges:
        if edge.edge_type == DependencyEdgeType.DRIVING_INPUT:
            driving = edge.upstream_key.name
    return {
        "name": model.key.name,
        "pipeline": model.pipeline_name,
        "kind": str(model.kind),
        "description": _model_description(model),
        "relationName": analysis.realized_project.relation_name_by_logical_key[model.key],
        "mvRelationName": _mv_relation_name(analysis=analysis, key=model.key),
        "drivingInput": driving,
        "refs": refs,
        "columns": _column_payloads(model),
        "storage": _storage_payload(model),
        "anchor": str(_anchor_reason(model)),
        "isAggregate": model.has_aggregate_semantics,
        "sql": _sql_payload(analysis=analysis, model=model, database=database),
    }


def _model_description(model: CompiledModel) -> str | None:
    if isinstance(model, CompiledTableModel):
        return model.transform.description
    if isinstance(model, CompiledViewModel):
        return model.view.description
    return None


def _authored_column_specs(model: CompiledModel) -> tuple[ModelColumnSpec, ...]:
    if isinstance(model, CompiledTableModel):
        return model.transform.columns
    if isinstance(model, CompiledViewModel):
        return model.view.columns
    return ()


def _column_payloads(model: CompiledModel) -> list[dict[str, object]]:
    described: dict[str, str | None] = {
        spec.name: spec.description for spec in _authored_column_specs(model)
    }
    return [
        {
            "name": column.name,
            "type": column.type,
            "description": described.get(column.name),
        }
        for column in model.output_columns
    ]


def _storage_payload(model: CompiledModel) -> dict[str, object] | None:
    if not isinstance(model, CompiledTableModel):
        return None
    return {
        "engine": model.transform.engine,
        "orderBy": list(model.transform.order_by),
        "partitionBy": model.transform.partition_by,
        "ttl": model.transform.ttl,
        "settings": None if model.transform.settings is None else dict(model.transform.settings),
    }


def _anchor_reason(model: CompiledModel) -> ReplayAnchorReason:
    if not isinstance(model, CompiledTableModel):
        return ReplayAnchorReason.VIEW
    if model.transform.replay_anchor == ReplayAnchorMode.NEVER:
        return ReplayAnchorReason.NEVER
    if model.has_mutable_refs:
        return ReplayAnchorReason.MUTABLE_REF
    if model.has_aggregate_semantics:
        return ReplayAnchorReason.AGGREGATE
    if not model.preserves_required_lineage:
        return ReplayAnchorReason.LINEAGE_LOSS
    return ReplayAnchorReason.ELIGIBLE


def _mv_relation_name(*, analysis: CompileAnalysis, key: LogicalResourceKey) -> str | None:
    resource: object
    for resource in analysis.realized_project.resources_by_logical_key.get(key, ()):
        if isinstance(resource, AdapterMaterializedView):
            return resource.name
    return None


def _sql_payload(
    *, analysis: CompileAnalysis, model: CompiledModel, database: str
) -> dict[str, object]:
    authored: str | None = _authored_file_contents(analysis=analysis, model=model)
    ddl: dict[str, str | None] = {"table": None, "materializedView": None, "view": None}
    field_by_type: dict[type, str] = {
        AdapterTable: "table",
        AdapterMaterializedView: "materializedView",
        AdapterView: "view",
    }
    resource: object
    for resource in analysis.realized_project.resources_by_logical_key.get(model.key, ()):
        field: str | None = field_by_type.get(type(resource))
        if field is not None:
            ddl[field] = analysis.adapter_profile.render_resource(
                resource=resource, database=database
            )
    return {
        "authored": authored,
        "compiled": analysis.realized_project.resolved_query_by_model_key.get(model.key),
        "ddl": ddl,
    }


def _authored_file_contents(*, analysis: CompileAnalysis, model: CompiledModel) -> str | None:
    source_path: Path | None = _model_source_path(model)
    if source_path is None:
        return None
    for discovered in analysis.discovered_inputs.model_files:
        if discovered.file_path == source_path:
            return discovered.contents
    return None


def _model_source_path(model: CompiledModel) -> Path | None:
    if isinstance(model, CompiledTableModel):
        return model.transform.source_file_path
    if isinstance(model, CompiledViewModel):
        return model.view.source_file_path
    return None


def _audit_payload(audit: LoadedSqlAudit) -> dict[str, object]:
    identity: QualityNodeIdentity | None = audit.quality_identity
    return {
        "name": audit.name or audit.file_path.stem,
        "file": str(audit.file_path),
        "severity": audit.severity,
        "description": audit.description,
        "genericName": audit.generic_definition_name,
        "referencedModels": list(audit.referenced_model_names),
        "sql": audit.query,
        "policy": {
            "cadenceSeconds": audit.cadence_seconds,
            "warmupSeconds": audit.warmup_seconds,
            "scheduled": audit.scheduled,
        },
        "identity": (
            None
            if identity is None
            else {
                "bindingKey": identity.binding_key,
                "definitionFingerprint": identity.definition_fingerprint,
                "executionFingerprint": identity.execution_fingerprint,
            }
        ),
    }


def _test_payload(test_case: SqlTestCase) -> dict[str, object]:
    identity: QualityNodeIdentity | None = test_case.quality_identity
    return {
        "name": test_case.name or test_case.file_path.stem,
        "file": str(test_case.file_path),
        "targets": [target.target_model_name for target in test_case.target_cases],
        "sql": test_case.query,
        "identity": (
            None
            if identity is None
            else {
                "bindingKey": identity.binding_key,
                "definitionFingerprint": identity.definition_fingerprint,
                "executionFingerprint": identity.execution_fingerprint,
            }
        ),
    }


def _macro_payloads(analysis: CompileAnalysis) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for name, macro in sorted(analysis.compiled_project.macro_registry.macros.items()):
        payloads.append(
            {
                "name": name,
                "file": str(macro.relative_path),
                "source": macro.source,
                "description": macro.description,
            }
        )
    return payloads
