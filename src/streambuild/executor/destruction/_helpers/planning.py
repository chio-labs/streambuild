"""Read-only assembly of frozen destruction plans."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterManagedSource,
    AdapterManifestResource,
    AdapterManifestSnapshot,
    AdapterMaterializedView,
    AdapterQueryResult,
    AdapterTable,
    AdapterView,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.adapter.types import AdapterOptionalStateStatus
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import DesiredObjectType, LogicalResourceType
from streambuild.compiler.graph.constants import ALL_DEPENDENCY_EDGE_TYPES
from streambuild.compiler.graph.main.collect_reachable_keys import collect_reachable_keys
from streambuild.compiler.graph.types import GraphTraversalDirection
from streambuild.compiler.manifest.constants import MANIFEST_VERSION
from streambuild.compiler.manifest.main.resolve_manifest_project_identity import (
    resolve_manifest_project_identity,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.destruction._helpers.ordering import (
    reverse_topologically_order_relations,
)
from streambuild.executor.destruction.classes.owned_relation import OwnedRelation
from streambuild.executor.destruction.constants import (
    CATALOG_MATERIALIZED_VIEW_ENGINE,
    CATALOG_VIEW_ENGINE,
    DEFAULT_DESTRUCTION_PLAN_TTL,
    MAX_NAMED_CHALLENGES,
    METADATA_RELATION_PREFIX,
    PRODUCTION_TARGET_NAMES,
)
from streambuild.executor.destruction.exceptions import (
    DestructionDependencyError,
    DestructionExternalDependencyError,
    DestructionResourceError,
    DestructionSelectionError,
    DestructionValidationError,
)
from streambuild.executor.destruction.models import (
    DestructionPlan,
    DestructionPlanParts,
    DestructionRelationEvidence,
    DestructionRequest,
)
from streambuild.executor.destruction.types import (
    DestructionOperation,
    DestructionOwnership,
    DestructionPlanningConnection,
    DestructionRelationKind,
)


def plan_destruction(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
    now: datetime | None = None,
    ttl: timedelta = DEFAULT_DESTRUCTION_PLAN_TTL,
    plan_id: str | None = None,
) -> DestructionPlan:
    """Build a frozen impact plan using only read-only adapter interactions."""

    created_at: datetime = _validated_created_at(now=now, ttl=ttl)
    pipeline_names: tuple[str, ...] = _available_pipeline_names(
        request=request,
        analysis=analysis,
    )
    requested: tuple[str, ...]
    included: tuple[str, ...]
    affected: tuple[str, ...]
    requested, included, affected = _resolve_pipeline_selection(
        request=request,
        analysis=analysis,
        available_pipeline_names=pipeline_names,
    )
    affected_model_names: tuple[str, ...]
    affected_source_names: tuple[str, ...]
    relations: tuple[DestructionRelationEvidence, ...]
    relation_drop_size_connection_limit: int | None = connection.load_relation_drop_size_limit()
    relation_drop_size_server_limit: int | None = (
        connection.load_relation_drop_size_server_default()
    )
    relation_drop_size_override: int | None = (
        analysis.compiled_project.destruction_relation_drop_size_limit
    )
    relation_drop_size_limit: int | None = (
        relation_drop_size_override
        if relation_drop_size_override is not None
        else relation_drop_size_connection_limit
    )
    affected_model_names, affected_source_names, relations = _plan_relation_evidence(
        request=request,
        analysis=analysis,
        connection=connection,
        affected_pipeline_names=affected,
        relation_drop_size_limit=relation_drop_size_limit,
    )
    challenges: tuple[str, ...] = build_destruction_challenges(
        pipeline_names=affected,
        production_reset=(
            request.operation == DestructionOperation.RESET_TARGET
            and (
                request.target.casefold() in PRODUCTION_TARGET_NAMES
                or getattr(
                    getattr(analysis, "compiled_project", None),
                    "production_target",
                    False,
                )
            )
        ),
    )
    manifest_fingerprint: str = _fingerprint(_manifest_payload(analysis=analysis))
    parts: DestructionPlanParts = DestructionPlanParts(
        plan_id=plan_id,
        created_at=created_at,
        ttl=ttl,
        requested_pipeline_names=requested,
        included_dependent_pipeline_names=included,
        affected_pipeline_names=affected,
        affected_model_names=affected_model_names,
        affected_source_names=affected_source_names,
        relations=relations,
        challenges=challenges,
        manifest_fingerprint=manifest_fingerprint,
        relation_drop_size_limit=relation_drop_size_limit,
        relation_drop_size_server_limit=relation_drop_size_server_limit,
        relation_drop_size_override=relation_drop_size_override,
        relation_drop_size_policy_observed=True,
        include_orphans=request.include_orphans,
    )
    return _build_plan(
        request=request,
        parts=parts,
    )


def _validated_created_at(*, now: datetime | None, ttl: timedelta) -> datetime:
    created_at: datetime = now or datetime.now(tz=UTC)
    if created_at.tzinfo is None:
        raise DestructionValidationError("Destruction plan timestamps must be timezone-aware")
    if ttl <= timedelta(0):
        raise DestructionValidationError("Destruction plan TTL must be positive")
    return created_at


def _available_pipeline_names(
    *, request: DestructionRequest, analysis: CompileAnalysis
) -> tuple[str, ...]:
    pipeline_names: tuple[str, ...] = tuple(
        sorted(pipeline.pipeline.name for pipeline in analysis.realized_project.project.pipelines)
    )
    compiled_target: str | None = analysis.realized_project.project.target_name
    if compiled_target is not None and request.target != compiled_target:
        raise DestructionSelectionError(
            f"Requested target {request.target!r} does not match compiled target "
            f"{compiled_target!r}"
        )
    return pipeline_names


def _plan_relation_evidence(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
    affected_pipeline_names: tuple[str, ...],
    relation_drop_size_limit: int | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[DestructionRelationEvidence, ...],
]:
    models: tuple[CompiledModel, ...] = tuple(
        sorted(
            (
                model
                for model in analysis.realized_project.project.models
                if model.pipeline_name in affected_pipeline_names
            ),
            key=lambda model: model.key.name,
        )
    )
    affected_model_names: tuple[str, ...] = tuple(model.key.name for model in models)
    source_keys: frozenset[LogicalResourceKey]
    affected_source_names: tuple[str, ...]
    source_keys, affected_source_names = _affected_sources(
        request=request,
        analysis=analysis,
        affected_pipeline_names=affected_pipeline_names,
    )
    logical_pipeline_names: dict[str, tuple[str, ...]] = _pipeline_names_by_logical_name(
        analysis=analysis
    )
    catalog: CatalogSnapshot = connection.load_catalog(request.database)
    owned: dict[str, OwnedRelation] = _manifest_owned_relations(
        analysis=analysis,
        models=models,
        source_keys=source_keys,
        logical_pipeline_names=logical_pipeline_names,
    )

    inventory: AdapterDeploymentInventory = connection.load_deployment_inventory(
        request.metadata_database
    )
    if request.operation == DestructionOperation.RESET_TARGET:
        recorded_logical_names: set[str] = set()
        for deployment in inventory.deployments:
            for mapping in deployment.prepared_object_mappings:
                recorded_logical_names.add(mapping.logical_model_name)
        affected_model_names = tuple(
            sorted(
                set(affected_model_names) | (recorded_logical_names - set(affected_source_names))
            )
        )
    affected_logical_names: frozenset[str] = frozenset(
        (*affected_model_names, *affected_source_names)
    )
    owned = _add_virtual_inventory_relations(
        owned=owned,
        inventory=inventory,
        database=request.database,
        affected_logical_names=affected_logical_names,
        logical_pipeline_names=logical_pipeline_names,
        include_all=request.operation == DestructionOperation.RESET_TARGET,
    )
    if request.include_orphans:
        owned = _add_historical_manifest_relations(
            owned=owned,
            request=request,
            analysis=analysis,
            connection=connection,
            catalog=catalog,
            affected_pipeline_names=frozenset(affected_pipeline_names),
        )
    stats: dict[str, tuple[int, int]] = _load_relation_stats(
        connection=connection,
        database=request.database,
        relation_names=tuple(sorted(owned)),
    )
    relations: tuple[DestructionRelationEvidence, ...] = _build_evidence(
        database=request.database,
        owned=owned,
        catalog=catalog,
        stats=stats,
    )
    _validate_drop_size_limit(limit=relation_drop_size_limit, relations=relations)
    _validate_external_dependants(
        connection=connection,
        database=request.database,
        owned_relation_names=frozenset(owned),
    )
    _ = reverse_topologically_order_relations(relations)
    return affected_model_names, affected_source_names, relations


def _validate_drop_size_limit(
    *,
    limit: int | None,
    relations: tuple[DestructionRelationEvidence, ...],
) -> None:
    if limit is None:
        return
    oversized: tuple[DestructionRelationEvidence, ...] = tuple(
        relation
        for relation in relations
        if relation.exists and relation.total_bytes is not None and relation.total_bytes > limit
    )
    if not oversized:
        return
    details: str = ", ".join(
        f"{relation.database}.{relation.name} ({relation.total_bytes:,} bytes)"
        for relation in oversized
    )
    raise DestructionResourceError(
        f"Warehouse relation DROP limit is {limit:,} bytes; oversized resources block "
        f"destruction before mutation: {details}"
    )


def _validate_external_dependants(
    *,
    connection: DestructionPlanningConnection,
    database: str,
    owned_relation_names: frozenset[str],
) -> None:
    blocked: tuple[str, ...] = connection.load_external_dependants(
        database=database,
        relation_names=tuple(sorted(owned_relation_names)),
    )
    if blocked:
        raise DestructionExternalDependencyError(tuple(sorted(set(blocked))))


def _catalog_dependency_names(relation: CatalogRelation) -> frozenset[str]:
    return frozenset(
        dependency
        for dependency in (
            *relation.source_relation_names,
            relation.target_relation_name,
            relation.stable_binding_name,
        )
        if dependency is not None
    )


def _build_plan(
    *,
    request: DestructionRequest,
    parts: DestructionPlanParts,
) -> DestructionPlan:
    plan_payload: dict[str, object] = {
        "operation": request.operation,
        "target": request.target,
        "database": request.database,
        "metadata_database": request.metadata_database,
        "requested_pipeline_names": parts.requested_pipeline_names,
        "included_dependent_pipeline_names": parts.included_dependent_pipeline_names,
        "affected_pipeline_names": parts.affected_pipeline_names,
        "affected_model_names": parts.affected_model_names,
        "affected_source_names": parts.affected_source_names,
        "relations": tuple(_structural_relation_payload(relation) for relation in parts.relations),
        "challenges": parts.challenges,
        "preserves_sources": False,
        "preserves_replay_data": False,
        "manifest_fingerprint": parts.manifest_fingerprint,
        "relation_drop_size_limit": parts.relation_drop_size_limit,
        "relation_drop_size_server_limit": parts.relation_drop_size_server_limit,
        "relation_drop_size_override": parts.relation_drop_size_override,
        "relation_drop_size_policy_observed": parts.relation_drop_size_policy_observed,
    }
    if parts.include_orphans:
        plan_payload["include_orphans"] = True
    return DestructionPlan(
        plan_id=parts.plan_id or f"destruction_{uuid4().hex}",
        operation=DestructionOperation(request.operation),
        target=request.target,
        database=request.database,
        metadata_database=request.metadata_database,
        requested_pipeline_names=parts.requested_pipeline_names,
        included_dependent_pipeline_names=parts.included_dependent_pipeline_names,
        affected_pipeline_names=parts.affected_pipeline_names,
        affected_model_names=parts.affected_model_names,
        affected_source_names=parts.affected_source_names,
        relations=parts.relations,
        challenges=parts.challenges,
        preserves_sources=False,
        preserves_replay_data=False,
        manifest_fingerprint=parts.manifest_fingerprint,
        plan_fingerprint=_fingerprint(plan_payload),
        created_at=parts.created_at,
        expires_at=parts.created_at + parts.ttl,
        relation_drop_size_limit=parts.relation_drop_size_limit,
        relation_drop_size_server_limit=parts.relation_drop_size_server_limit,
        relation_drop_size_override=parts.relation_drop_size_override,
        relation_drop_size_policy_observed=parts.relation_drop_size_policy_observed,
        include_orphans=parts.include_orphans,
    )


def build_destruction_challenges(
    *, pipeline_names: tuple[str, ...], production_reset: bool = False
) -> tuple[str, ...]:
    """Return stable, ordered challenge values for the affected pipeline set."""

    names: tuple[str, ...] = tuple(sorted(set(pipeline_names)))
    if not names:
        raise DestructionSelectionError(
            "Destructive execution requires at least one attributable pipeline challenge"
        )
    selected: tuple[str, ...]
    if len(names) <= MAX_NAMED_CHALLENGES:
        selected = names
    else:
        selected = (names[0], names[len(names) // 2], names[-1])
    if production_reset:
        return (*selected, "PRODUCTION")
    return selected


def _resolve_pipeline_selection(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    available_pipeline_names: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    available: frozenset[str] = frozenset(available_pipeline_names)
    if request.operation == DestructionOperation.RESET_TARGET:
        if request.pipeline_names or request.included_dependent_pipeline_names:
            raise DestructionSelectionError("Target reset does not accept a pipeline selection")
        return (), (), available_pipeline_names
    if not request.pipeline_names:
        raise DestructionSelectionError("Pipeline destruction requires at least one pipeline")
    supplied: frozenset[str] = frozenset(
        (*request.pipeline_names, *request.included_dependent_pipeline_names)
    )
    unknown: tuple[str, ...] = tuple(sorted(supplied - available))
    if unknown:
        raise DestructionSelectionError(f"Unknown pipelines: {unknown!r}")

    pipeline_by_model_key: dict[LogicalResourceKey, str] = {
        model.key: model.pipeline_name for model in analysis.realized_project.project.models
    }
    required_pipeline_names: set[str] = set(supplied)
    while True:
        root_keys: frozenset[LogicalResourceKey] = frozenset(
            model.key
            for model in analysis.realized_project.project.models
            if model.pipeline_name in required_pipeline_names
        )
        reachable: tuple[LogicalResourceKey, ...] = collect_reachable_keys(
            graph=analysis.graph,
            root_keys=root_keys,
            direction=GraphTraversalDirection.DOWNSTREAM,
            edge_types=ALL_DEPENDENCY_EDGE_TYPES,
        )
        expanded_pipeline_names: set[str] = set(required_pipeline_names)
        expanded_pipeline_names.update(
            pipeline_by_model_key[key] for key in reachable if key in pipeline_by_model_key
        )
        expanded_pipeline_names.update(
            _shared_source_pipeline_names(
                analysis=analysis,
                pipeline_names=frozenset(required_pipeline_names),
            )
        )
        if expanded_pipeline_names == required_pipeline_names:
            break
        required_pipeline_names = expanded_pipeline_names
    required_dependents: frozenset[str] = frozenset(
        required_pipeline_names - set(request.pipeline_names)
    )
    missing: tuple[str, ...] = tuple(
        sorted(required_dependents - set(request.included_dependent_pipeline_names))
    )
    if missing:
        raise DestructionDependencyError(missing)
    affected: tuple[str, ...] = tuple(sorted(supplied))
    return request.pipeline_names, request.included_dependent_pipeline_names, affected


def _affected_sources(
    *,
    request: DestructionRequest,
    analysis: CompileAnalysis,
    affected_pipeline_names: tuple[str, ...],
) -> tuple[frozenset[LogicalResourceKey], tuple[str, ...]]:
    managed_source_keys: frozenset[LogicalResourceKey] = frozenset(
        source.key
        for source in analysis.realized_project.project.sources
        if analysis.realized_project.resources_by_logical_key.get(source.key, ())
    )
    if request.operation == DestructionOperation.RESET_TARGET:
        selected_source_keys: frozenset[LogicalResourceKey] = managed_source_keys
    else:
        model_keys: frozenset[LogicalResourceKey] = frozenset(
            model.key
            for model in analysis.realized_project.project.models
            if model.pipeline_name in affected_pipeline_names
        )
        upstream_keys: frozenset[LogicalResourceKey] = frozenset(
            collect_reachable_keys(
                graph=analysis.graph,
                root_keys=model_keys,
                direction=GraphTraversalDirection.UPSTREAM,
                edge_types=ALL_DEPENDENCY_EDGE_TYPES,
            )
        )
        declared_source_keys: frozenset[LogicalResourceKey] = frozenset(
            pipeline.source.key
            for pipeline in analysis.realized_project.project.pipelines
            if pipeline.pipeline.name in affected_pipeline_names and pipeline.source is not None
        )
        selected_source_keys = managed_source_keys & (upstream_keys | declared_source_keys)
    return selected_source_keys, tuple(sorted(key.name for key in selected_source_keys))


def _shared_source_pipeline_names(
    *, analysis: CompileAnalysis, pipeline_names: frozenset[str]
) -> frozenset[str]:
    managed_source_names: frozenset[str] = frozenset(
        source.key.name
        for source in analysis.realized_project.project.sources
        if analysis.realized_project.resources_by_logical_key.get(source.key, ())
    )
    source_names: set[str] = {
        pipeline.source.key.name
        for pipeline in analysis.realized_project.project.pipelines
        if pipeline.pipeline.name in pipeline_names
        and pipeline.source is not None
        and pipeline.source.key.name in managed_source_names
    }
    selected_model_keys: frozenset[LogicalResourceKey] = frozenset(
        model.key
        for model in analysis.realized_project.project.models
        if model.pipeline_name in pipeline_names
    )
    upstream_keys: tuple[LogicalResourceKey, ...] = collect_reachable_keys(
        graph=analysis.graph,
        root_keys=selected_model_keys,
        direction=GraphTraversalDirection.UPSTREAM,
        edge_types=ALL_DEPENDENCY_EDGE_TYPES,
    )
    source_names.update(
        key.name
        for key in upstream_keys
        if key.resource_type == LogicalResourceType.SOURCE and key.name in managed_source_names
    )
    pipeline_names_by_logical_name: dict[str, tuple[str, ...]] = _pipeline_names_by_logical_name(
        analysis=analysis
    )
    shared_pipeline_names: set[str] = set()
    for source_name in source_names:
        shared_pipeline_names.update(pipeline_names_by_logical_name.get(source_name, ()))
    return frozenset(shared_pipeline_names)


def _pipeline_names_by_logical_name(*, analysis: CompileAnalysis) -> dict[str, tuple[str, ...]]:
    names: dict[str, set[str]] = {}
    pipeline_by_model_key: dict[LogicalResourceKey, str] = {
        model.key: model.pipeline_name for model in analysis.realized_project.project.models
    }
    for model in analysis.realized_project.project.models:
        names.setdefault(model.key.name, set()).add(model.pipeline_name)
    for pipeline in analysis.realized_project.project.pipelines:
        if pipeline.source is not None:
            names.setdefault(pipeline.source.key.name, set()).add(pipeline.pipeline.name)
    for source in analysis.realized_project.project.sources:
        downstream_keys: tuple[LogicalResourceKey, ...] = collect_reachable_keys(
            graph=analysis.graph,
            root_keys=frozenset((source.key,)),
            direction=GraphTraversalDirection.DOWNSTREAM,
            edge_types=ALL_DEPENDENCY_EDGE_TYPES,
        )
        names.setdefault(source.key.name, set()).update(
            pipeline_by_model_key[key] for key in downstream_keys if key in pipeline_by_model_key
        )
    return {name: tuple(sorted(values)) for name, values in names.items()}


def _manifest_owned_relations(
    *,
    analysis: CompileAnalysis,
    models: tuple[CompiledModel, ...],
    source_keys: frozenset[LogicalResourceKey],
    logical_pipeline_names: Mapping[str, tuple[str, ...]],
) -> dict[str, OwnedRelation]:
    owned: dict[str, OwnedRelation] = {}
    selected_keys: set[LogicalResourceKey] = {model.key for model in models} | set(source_keys)
    for key in sorted(selected_keys, key=lambda value: (value.resource_type, value.name)):
        for resource in analysis.realized_project.resources_by_logical_key.get(key, ()):
            name: str = resource.name
            if _excluded_metadata_relation(name):
                continue
            _add_associated_relation(
                owned=owned,
                name=name,
                kind=_resource_kind(resource),
                logical_name=key.name,
                pipeline_names=logical_pipeline_names.get(key.name, ()),
                ownership=DestructionOwnership.CURRENT_MANIFEST,
            )
    return owned


def _add_historical_manifest_relations(
    *,
    owned: dict[str, OwnedRelation],
    request: DestructionRequest,
    analysis: CompileAnalysis,
    connection: DestructionPlanningConnection,
    catalog: CatalogSnapshot,
    affected_pipeline_names: frozenset[str],
) -> dict[str, OwnedRelation]:
    current_resource_names: frozenset[str] = _current_manifest_resource_names(analysis=analysis)
    snapshot: AdapterManifestSnapshot = connection.load_manifests(
        database=request.metadata_database,
        project_identity=resolve_manifest_project_identity(analysis=analysis),
        target_name=request.target,
        target_database=request.database,
    )
    if snapshot.status == AdapterOptionalStateStatus.UNAVAILABLE:
        raise DestructionResourceError(snapshot.warning or "Manifest history is unavailable")
    if snapshot.status == AdapterOptionalStateStatus.ABSENT:
        return owned
    historical_resources: set[AdapterManifestResource] = _eligible_historical_resources(
        snapshot=snapshot,
        affected_pipeline_names=affected_pipeline_names,
        database=request.database,
        current_resource_names=current_resource_names,
        catalog=catalog,
    )
    for resource in sorted(
        historical_resources,
        key=lambda value: (
            value.resource_name,
            value.pipeline_name,
            value.logical_name,
        ),
    ):
        try:
            kind: DestructionRelationKind = DestructionRelationKind(resource.resource_kind)
        except ValueError as error:
            raise DestructionResourceError(
                f"Unsupported historical manifest resource kind {resource.resource_kind!r} "
                f"for {resource.resource_name!r}"
            ) from error
        _add_owned_relation(
            owned=owned,
            name=resource.resource_name,
            kind=kind,
            logical_name=resource.logical_name,
            pipeline_name=resource.pipeline_name,
            ownership=DestructionOwnership.HISTORICAL_MANIFEST,
        )
    return owned


def _current_manifest_resource_names(*, analysis: CompileAnalysis) -> frozenset[str]:
    names: set[str] = set()
    for resources in analysis.realized_project.resources_by_logical_key.values():
        names.update(
            resource.name
            for resource in resources
            if not _excluded_metadata_relation(resource.name)
        )
    return frozenset(names)


def _eligible_historical_resources(
    *,
    snapshot: AdapterManifestSnapshot,
    affected_pipeline_names: frozenset[str],
    database: str,
    current_resource_names: frozenset[str],
    catalog: CatalogSnapshot,
) -> set[AdapterManifestResource]:
    if not snapshot.manifests:
        return set()
    published_current_names: frozenset[str] = frozenset(
        resource.resource_name for resource in snapshot.manifests[0].resources
    )
    protected_current_names: frozenset[str] = current_resource_names | published_current_names
    latest_resources_by_name: dict[str, set[AdapterManifestResource]] = {}
    for manifest in snapshot.manifests:
        if manifest.manifest_version != MANIFEST_VERSION:
            raise DestructionResourceError(
                f"Unsupported manifest version {manifest.manifest_version}; "
                f"expected {MANIFEST_VERSION}"
            )
        resources_by_name: dict[str, set[AdapterManifestResource]] = {}
        for resource in manifest.resources:
            resources_by_name.setdefault(resource.resource_name, set()).add(resource)
        for name, resources in resources_by_name.items():
            latest_resources_by_name.setdefault(name, resources)
    eligible: set[AdapterManifestResource] = set()
    for name, resources in latest_resources_by_name.items():
        if name in protected_current_names or _excluded_metadata_relation(name):
            continue
        if catalog.relation(name) is None:
            continue
        for resource in resources:
            if resource.pipeline_name not in affected_pipeline_names:
                continue
            if resource.resource_database != database:
                continue
            eligible.add(resource)
    return eligible


def _add_virtual_inventory_relations(
    *,
    owned: dict[str, OwnedRelation],
    inventory: AdapterDeploymentInventory,
    database: str,
    affected_logical_names: frozenset[str],
    logical_pipeline_names: Mapping[str, tuple[str, ...]],
    include_all: bool,
) -> dict[str, OwnedRelation]:
    logical_name_by_published_name: dict[str, str] = {}
    for deployment in sorted(inventory.deployments, key=lambda value: value.deployment_id):
        for mapping in sorted(
            deployment.prepared_object_mappings,
            key=lambda value: (value.physical_name, value.logical_key.name),
        ):
            logical_name_by_published_name[mapping.logical_key.name] = mapping.logical_model_name
            logical_name_by_published_name[mapping.physical_name] = mapping.logical_model_name
            if not include_all and mapping.logical_model_name not in affected_logical_names:
                continue
            if mapping.logical_key.database not in {None, database}:
                raise DestructionResourceError(
                    "Destruction cannot mutate recorded virtual resources outside the target "
                    f"database: {mapping.logical_key.database}.{mapping.physical_name}"
                )
            if _excluded_metadata_relation(mapping.physical_name):
                continue
            _add_associated_relation(
                owned=owned,
                name=mapping.physical_name,
                kind=_object_type_kind(mapping.logical_key.object_type),
                logical_name=mapping.logical_model_name,
                pipeline_names=logical_pipeline_names.get(mapping.logical_model_name, ()),
                ownership=DestructionOwnership.VIRTUAL_PHYSICAL_MAPPING,
            )
    for event in sorted(
        inventory.publish_events, key=lambda value: (value.published_at, value.deployment_id)
    ):
        for binding in sorted(
            event.bindings,
            key=lambda value: (value.logical_name, value.database),
        ):
            if binding.database != database:
                continue
            if _excluded_metadata_relation(binding.logical_name):
                continue
            logical_name: str = logical_name_by_published_name.get(
                binding.logical_name,
                binding.logical_name,
            )
            if binding.logical_name in owned:
                logical_name = sorted(owned[binding.logical_name].logical_names)[0]
            if not include_all and logical_name not in affected_logical_names:
                continue
            _add_associated_relation(
                owned=owned,
                name=binding.logical_name,
                kind=DestructionRelationKind.VIEW,
                logical_name=logical_name,
                pipeline_names=logical_pipeline_names.get(logical_name, ()),
                ownership=DestructionOwnership.PUBLISHED_STABLE_BINDING,
            )
            if not _excluded_metadata_relation(binding.physical_name):
                _add_associated_relation(
                    owned=owned,
                    name=binding.physical_name,
                    kind=DestructionRelationKind.TABLE,
                    logical_name=logical_name_by_published_name.get(
                        binding.physical_name,
                        logical_name,
                    ),
                    pipeline_names=logical_pipeline_names.get(logical_name, ()),
                    ownership=DestructionOwnership.VIRTUAL_PHYSICAL_MAPPING,
                )
    return owned


def _add_owned_relation(
    *,
    owned: dict[str, OwnedRelation],
    name: str,
    kind: DestructionRelationKind,
    logical_name: str,
    pipeline_name: str | None,
    ownership: DestructionOwnership,
) -> dict[str, OwnedRelation]:
    existing: OwnedRelation | None = owned.get(name)
    if existing is None:
        owned[name] = OwnedRelation(
            name=name,
            kind=kind,
            logical_name=logical_name,
            pipeline_name=pipeline_name,
            ownership=ownership,
        )
        return owned
    existing.merge(
        kind=kind,
        logical_name=logical_name,
        pipeline_name=pipeline_name,
        ownership=ownership,
        kind_rank=_drop_rank(kind),
        current_kind_rank=_drop_rank(existing.kind),
    )
    return owned


def _add_associated_relation(
    *,
    owned: dict[str, OwnedRelation],
    name: str,
    kind: DestructionRelationKind,
    logical_name: str,
    pipeline_names: tuple[str, ...],
    ownership: DestructionOwnership,
) -> None:
    associated_pipeline_names: tuple[str | None, ...] = pipeline_names or (None,)
    for pipeline_name in associated_pipeline_names:
        _add_owned_relation(
            owned=owned,
            name=name,
            kind=kind,
            logical_name=logical_name,
            pipeline_name=pipeline_name,
            ownership=ownership,
        )


def _load_relation_stats(
    *,
    connection: DestructionPlanningConnection,
    database: str,
    relation_names: tuple[str, ...],
) -> dict[str, tuple[int, int]]:
    if not relation_names:
        return {}
    names_sql: str = ", ".join(_quote_string(name) for name in relation_names)
    result: AdapterQueryResult = connection.query(
        "SELECT table AS relation_name, sum(bytes_on_disk) AS total_bytes, "
        "count() AS active_parts FROM system.parts WHERE active = 1 "
        f"AND database = {_quote_string(database)} AND table IN ({names_sql}) "
        "GROUP BY table ORDER BY table"
    )
    stats: dict[str, tuple[int, int]] = {}
    for row in result.named_rows():
        stats[str(row["relation_name"])] = (
            int(str(row["total_bytes"])),
            int(str(row["active_parts"])),
        )
    return stats


def _build_evidence(
    *,
    database: str,
    owned: Mapping[str, OwnedRelation],
    catalog: CatalogSnapshot,
    stats: Mapping[str, tuple[int, int]],
) -> tuple[DestructionRelationEvidence, ...]:
    evidence: list[DestructionRelationEvidence] = []
    for name in sorted(owned):
        relation: OwnedRelation = owned[name]
        catalog_relation: CatalogRelation | None = catalog.relation(name)
        kind: DestructionRelationKind = _catalog_kind(
            relation=catalog_relation,
            fallback=relation.kind,
        )
        table_stats: tuple[int, int] | None = stats.get(name)
        exists: bool = catalog_relation is not None
        has_parts: bool = kind == DestructionRelationKind.TABLE
        evidence.append(
            DestructionRelationEvidence(
                database=database,
                name=name,
                kind=kind,
                exists=exists,
                total_bytes=(table_stats[0] if table_stats else 0)
                if has_parts and exists
                else None,
                active_parts=(table_stats[1] if table_stats else 0)
                if has_parts and exists
                else None,
                catalog_fingerprint=(
                    None if catalog_relation is None else catalog_relation.ownership_generation
                ),
                logical_names=tuple(sorted(relation.logical_names)),
                pipeline_names=tuple(sorted(relation.pipeline_names)),
                ownership=tuple(sorted(relation.ownership, key=lambda value: value.value)),
                dependency_relation_names=(
                    tuple(sorted(_catalog_dependency_names(catalog_relation) & owned.keys()))
                    if catalog_relation is not None
                    else ()
                ),
            )
        )
    return tuple(evidence)


def _structural_relation_payload(relation: DestructionRelationEvidence) -> dict[str, object]:
    """Exclude volatile footprint estimates from execution drift identity."""

    return {
        "database": relation.database,
        "name": relation.name,
        "kind": relation.kind,
        "exists": relation.exists,
        "catalog_fingerprint": relation.catalog_fingerprint,
        "logical_names": relation.logical_names,
        "pipeline_names": relation.pipeline_names,
        "ownership": relation.ownership,
        "dependency_relation_names": relation.dependency_relation_names,
    }


def _manifest_payload(*, analysis: CompileAnalysis) -> dict[str, object]:
    project: CompiledProject = analysis.realized_project.project
    return {
        "project_name": project.project_name,
        "target_name": project.target_name,
        "effective_target": getattr(
            getattr(analysis, "compile_inputs", None), "effective_target", None
        ),
        "variables": getattr(getattr(analysis, "compile_inputs", None), "variables", ()),
        "access_policy_fingerprint": getattr(
            getattr(analysis, "access_policy", None), "fingerprint", None
        ),
        "pipelines": tuple(sorted(pipeline.pipeline.name for pipeline in project.pipelines)),
        "models": tuple(
            {
                "name": model.key.name,
                "pipeline": model.pipeline_name,
                "kind": model.kind,
                "relation_name": analysis.realized_project.relation_name_by_logical_key.get(
                    model.key
                ),
                "query": analysis.realized_project.resolved_query_by_model_key.get(model.key),
                "resources": analysis.realized_project.resources_by_logical_key.get(model.key, ()),
            }
            for model in sorted(project.models, key=lambda value: value.key.name)
        ),
        "sources": tuple(
            {
                "name": source.key.name,
                "definition": getattr(source, "source", None),
                "relation_name": analysis.realized_project.relation_name_by_logical_key.get(
                    source.key
                ),
                "resources": analysis.realized_project.resources_by_logical_key.get(source.key, ()),
            }
            for source in sorted(project.sources, key=lambda value: value.key.name)
        ),
        "edges": _manifest_edges(analysis=analysis),
    }


def _manifest_edges(*, analysis: CompileAnalysis) -> tuple[tuple[str, str, object], ...]:
    edge_payloads: list[tuple[str, str, object]] = []
    for edges in analysis.graph.downstream_edges_by_key.values():
        for edge in edges:
            edge_payloads.append(
                (
                    edge.upstream_key.name,
                    edge.downstream_key.name,
                    edge.edge_type,
                )
            )
    return tuple(sorted(edge_payloads, key=lambda value: (value[0], value[1], str(value[2]))))


def _resource_kind(resource: object) -> DestructionRelationKind:
    if isinstance(resource, AdapterView):
        return DestructionRelationKind.VIEW
    if isinstance(resource, AdapterMaterializedView):
        return DestructionRelationKind.MATERIALIZED_VIEW
    if isinstance(resource, AdapterManagedSource):
        return DestructionRelationKind.MANAGED_SOURCE
    if isinstance(resource, AdapterTable):
        return DestructionRelationKind.TABLE
    raise DestructionResourceError(f"Unsupported manifest resource: {type(resource).__name__}")


def _object_type_kind(object_type: DesiredObjectType | str) -> DestructionRelationKind:
    value: DesiredObjectType = DesiredObjectType(object_type)
    if value == DesiredObjectType.VIEW:
        return DestructionRelationKind.VIEW
    if value == DesiredObjectType.MATERIALIZED_VIEW:
        return DestructionRelationKind.MATERIALIZED_VIEW
    if value == DesiredObjectType.KAFKA_TABLE:
        return DestructionRelationKind.MANAGED_SOURCE
    return DestructionRelationKind.TABLE


def _catalog_kind(
    *, relation: CatalogRelation | None, fallback: DestructionRelationKind
) -> DestructionRelationKind:
    if relation is None:
        return fallback
    if relation.engine == CATALOG_VIEW_ENGINE:
        return DestructionRelationKind.VIEW
    if relation.engine == CATALOG_MATERIALIZED_VIEW_ENGINE:
        return DestructionRelationKind.MATERIALIZED_VIEW
    return fallback


def _drop_rank(kind: DestructionRelationKind) -> int:
    return {
        DestructionRelationKind.VIEW: 0,
        DestructionRelationKind.MATERIALIZED_VIEW: 1,
        DestructionRelationKind.TABLE: 2,
        DestructionRelationKind.MANAGED_SOURCE: 2,
    }[kind]


def _excluded_metadata_relation(name: str) -> bool:
    return name.casefold().startswith(METADATA_RELATION_PREFIX)


def _quote_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _fingerprint(value: object) -> str:
    canonical: str = json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(canonical.encode()).hexdigest()


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        items: list[object] = [_canonical(item) for item in value]
        if isinstance(value, (set, frozenset)):
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        return items
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)
