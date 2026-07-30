"""Classify durable ownership evidence for direct-mode targets under D-019."""

from __future__ import annotations

from streambuild.adapter.models import AdapterOwnershipRecord, CatalogRelation
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)
from streambuild.compiler.planner.main.logical_name_from_physical_name import (
    logical_name_from_physical_name,
)
from streambuild.compiler.planner.models import (
    DirectWarehouseSnapshot,
    TargetOwnershipClassification,
)
from streambuild.compiler.planner.types import TargetOwnership


def classify_relation_ownership(
    *, snapshot: DirectWarehouseSnapshot, relation_names: tuple[str, ...]
) -> tuple[TargetOwnershipClassification, ...]:
    """Classify every requested relation from durable warehouse evidence."""

    direct_names: frozenset[str] = _owned_relation_names(
        records=snapshot.ownership_records,
        mode=AdapterOwningMode.DIRECT,
        database=snapshot.catalog.identity.database,
    )
    virtual_environment_names: frozenset[str] = _virtual_environment_names(snapshot=snapshot)
    existing_names: frozenset[str] = snapshot.catalog.relation_names()
    return tuple(
        TargetOwnershipClassification(
            relation_name=relation_name,
            ownership=_ownership_for(
                relation_name=relation_name,
                direct_names=direct_names,
                virtual_environment_names=virtual_environment_names,
                existing_names=existing_names,
            ),
        )
        for relation_name in relation_names
    )


def _ownership_for(
    *,
    relation_name: str,
    direct_names: frozenset[str],
    virtual_environment_names: frozenset[str],
    existing_names: frozenset[str],
) -> TargetOwnership:
    is_direct: bool = relation_name in direct_names
    is_virtual_environment: bool = relation_name in virtual_environment_names
    if is_direct and is_virtual_environment:
        return TargetOwnership.CONFLICTED
    if is_direct:
        return TargetOwnership.DIRECT
    if is_virtual_environment:
        return TargetOwnership.VIRTUAL_ENVIRONMENT
    if relation_name in existing_names:
        return TargetOwnership.UNMANAGED
    return TargetOwnership.ABSENT


def _owned_relation_names(
    *, records: tuple[AdapterOwnershipRecord, ...], mode: AdapterOwningMode, database: str
) -> frozenset[str]:
    return frozenset(
        record.relation_name
        for record in records
        if record.owning_mode == mode and record.database_name == database
    )


def _virtual_environment_names(*, snapshot: DirectWarehouseSnapshot) -> frozenset[str]:
    names: set[str] = set(
        _owned_relation_names(
            records=snapshot.ownership_records,
            mode=AdapterOwningMode.VIRTUAL_ENVIRONMENT,
            database=snapshot.catalog.identity.database,
        )
    )
    relation: CatalogRelation
    for relation in snapshot.catalog.relations:
        if relation.stable_binding_name is not None:
            names.add(relation.name)
        if is_deployment_physical_name(relation.name):
            names.add(logical_name_from_physical_name(relation.name))
    return frozenset(names)
