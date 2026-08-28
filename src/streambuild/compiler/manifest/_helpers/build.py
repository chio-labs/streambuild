"""Canonical project manifest construction."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterManifest,
    AdapterManifestResource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)
from streambuild.compiler.compile.models import LogicalResourceKey, LogicalResourceType
from streambuild.compiler.graph.constants import ALL_DEPENDENCY_EDGE_TYPES
from streambuild.compiler.graph.main.collect_reachable_keys import collect_reachable_keys
from streambuild.compiler.graph.types import GraphTraversalDirection
from streambuild.compiler.manifest.constants import MANIFEST_VERSION
from streambuild.compiler.manifest.types import ManifestAdapterResource
from streambuild.compiler.pipeline.models import CompileAnalysis


def build_manifest_record(
    *,
    analysis: CompileAnalysis,
    invocation_id: str,
    project_identity: str,
    target_database: str,
    tool_version: str,
    project_revision: str | None,
    published_at: str | None,
) -> AdapterManifest:
    """Return one complete, deterministically fingerprinted project manifest."""

    pipeline_names: tuple[str, ...] = tuple(
        sorted({pipeline.pipeline.name for pipeline in analysis.realized_project.project.pipelines})
    )
    resources: tuple[AdapterManifestResource, ...] = _manifest_resources(
        analysis=analysis,
        target_database=target_database,
    )
    target_name: str = analysis.realized_project.project.target_name or ""
    fingerprint: str = _manifest_fingerprint(
        project_identity=project_identity,
        target_name=target_name,
        target_database=target_database,
        is_production=analysis.realized_project.project.production_target,
        pipeline_names=pipeline_names,
        resources=resources,
    )
    return AdapterManifest(
        manifest_id=str(uuid4()),
        invocation_id=invocation_id,
        project_identity=project_identity,
        target_name=target_name,
        target_database=target_database,
        is_production=analysis.realized_project.project.production_target,
        project_revision=project_revision,
        manifest_fingerprint=fingerprint,
        manifest_version=MANIFEST_VERSION,
        pipelines=pipeline_names,
        resources=resources,
        tool_version=tool_version,
        published_at=published_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
    )


def _manifest_resources(
    *, analysis: CompileAnalysis, target_database: str
) -> tuple[AdapterManifestResource, ...]:
    pipeline_names_by_key: dict[LogicalResourceKey, tuple[str, ...]] = (
        _pipeline_names_by_logical_key(analysis=analysis)
    )
    resources: list[AdapterManifestResource] = []
    for key, realized_resources in analysis.realized_project.resources_by_logical_key.items():
        for resource in realized_resources:
            for pipeline_name in pipeline_names_by_key.get(key, ()):
                resources.append(
                    AdapterManifestResource(
                        pipeline_name=pipeline_name,
                        logical_type=str(key.resource_type),
                        logical_name=key.name,
                        resource_role=_resource_role(
                            logical_type=LogicalResourceType(key.resource_type),
                            resource=resource,
                        ),
                        resource_database=target_database,
                        resource_name=resource.name,
                        resource_kind=_resource_kind(resource),
                    )
                )
    return tuple(sorted(resources, key=_resource_identity))


def _pipeline_names_by_logical_key(
    *, analysis: CompileAnalysis
) -> dict[LogicalResourceKey, tuple[str, ...]]:
    names: dict[LogicalResourceKey, set[str]] = {}
    for pipeline in analysis.realized_project.project.pipelines:
        if pipeline.source is not None:
            names.setdefault(pipeline.source.key, set()).add(pipeline.pipeline.name)
        for model in pipeline.models:
            names.setdefault(model.key, set()).add(pipeline.pipeline.name)
    pipeline_name_by_model_key: dict[LogicalResourceKey, str] = {
        model.key: model.pipeline_name for model in analysis.realized_project.project.models
    }
    for source in analysis.realized_project.project.sources:
        downstream_keys: tuple[LogicalResourceKey, ...] = collect_reachable_keys(
            graph=analysis.graph,
            root_keys=frozenset((source.key,)),
            direction=GraphTraversalDirection.DOWNSTREAM,
            edge_types=ALL_DEPENDENCY_EDGE_TYPES,
        )
        names.setdefault(source.key, set()).update(
            pipeline_name_by_model_key[key]
            for key in downstream_keys
            if key in pipeline_name_by_model_key
        )
    return {key: tuple(sorted(values)) for key, values in names.items()}


def _manifest_fingerprint(
    *,
    project_identity: str,
    target_name: str,
    target_database: str,
    is_production: bool,
    pipeline_names: tuple[str, ...],
    resources: tuple[AdapterManifestResource, ...],
) -> str:
    payload: dict[str, object] = {
        "is_production": is_production,
        "pipelines": pipeline_names,
        "project_identity": project_identity,
        "resources": tuple(_resource_identity(resource) for resource in resources),
        "target_database": target_database,
        "target_name": target_name,
    }
    return sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _resource_kind(resource: ManifestAdapterResource) -> str:
    if isinstance(resource, AdapterManagedSource):
        return "managed_source"
    if isinstance(resource, AdapterTable):
        return "table"
    if isinstance(resource, AdapterView):
        return "view"
    return "materialized_view"


def _resource_role(*, logical_type: LogicalResourceType, resource: ManifestAdapterResource) -> str:
    if logical_type == LogicalResourceType.SOURCE:
        if isinstance(resource, AdapterManagedSource):
            return "source"
        if isinstance(resource, AdapterTable):
            return "landing"
        return "landing_view"
    if isinstance(resource, AdapterMaterializedView):
        return "materialization"
    return "primary"


def _resource_identity(resource: AdapterManifestResource) -> tuple[str, ...]:
    return (
        resource.pipeline_name,
        resource.logical_type,
        resource.logical_name,
        resource.resource_role,
        resource.resource_database,
        resource.resource_name,
        resource.resource_kind,
    )
