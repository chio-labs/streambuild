"""Deployment inventory payloads for the development UI."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import InspectedManagedTableState
from streambuild.compiler.compile.constants import MATERIALIZED_VIEW_NAME_PREFIX
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)
from streambuild.compiler.planner.main.logical_name_from_physical_name import (
    logical_name_from_physical_name,
)
from streambuild.dev_server._helpers.payloads.state_payload import build_relation_stats_query
from streambuild.dev_server.models import RelationStorage
from streambuild.executor.deployment.main.load_deployments import load_deployments
from streambuild.executor.deployment.models import DeploymentInventory, DeploymentSummary


def build_deployments_payload(
    *, connection: AdapterConnection, database: str, metadata_database: str
) -> dict[str, object]:
    """Return every reconstructed deployment with storage totals for the UI."""

    inventory: DeploymentInventory = load_deployments(
        client=connection,
        metadata_database=metadata_database,
        default_database=database,
    )
    storage: dict[str, RelationStorage] = read_relation_storage(
        connection=connection, database=database
    )
    return {
        "database": inventory.database,
        "deployments": [
            _summary_payload(deployment=deployment, storage=storage)
            for deployment in inventory.deployments
        ],
    }


def build_deployment_detail_payload(
    *,
    connection: AdapterConnection,
    database: str,
    metadata_database: str,
    deployment_id: str,
) -> dict[str, object] | None:
    """Return one deployment with per-model staged versus live comparison."""

    inventory: DeploymentInventory = load_deployments(
        client=connection,
        metadata_database=metadata_database,
        default_database=database,
    )
    deployment: DeploymentSummary | None = next(
        (item for item in inventory.deployments if item.deployment_id == deployment_id),
        None,
    )
    if deployment is None:
        return None
    storage: dict[str, RelationStorage] = read_relation_storage(
        connection=connection, database=database
    )
    inspected: InspectedManagedTableState = connection.inspect_managed_table_state(database)
    live_by_logical: dict[str, str] = {
        binding.logical_name: binding.physical_name for binding in inspected.active_bindings
    }
    models: list[dict[str, object]] = _model_payloads(
        deployment=deployment,
        live_by_logical=live_by_logical,
        storage=storage,
    )
    return {
        "database": database,
        **_summary_payload(deployment=deployment, storage=storage),
        "models": models,
        "wouldOrphan": _would_orphan_payload(
            deployment=deployment,
            live_by_logical=live_by_logical,
            storage=storage,
            models=models,
        ),
    }


def read_relation_storage(
    *, connection: AdapterConnection, database: str
) -> dict[str, RelationStorage]:
    """Return row and byte totals per relation; empty when storage is unreadable."""

    try:
        rows: tuple[Mapping[str, object], ...] = connection.query(
            build_relation_stats_query(database=database)
        ).named_rows()
    except AdapterError:
        return {}
    return {
        str(row["name"]): RelationStorage(
            rows=_as_int(row["total_rows"]),
            bytes=_as_int(row["total_bytes"]),
        )
        for row in rows
    }


def _summary_payload(
    *, deployment: DeploymentSummary, storage: Mapping[str, RelationStorage]
) -> dict[str, object]:
    totals: RelationStorage = _storage_total(
        relation_names=deployment.physical_relation_names, storage=storage
    )
    model_relations: tuple[str, ...] = _model_relation_names(deployment.physical_relation_names)
    return {
        "deploymentId": deployment.deployment_id,
        "state": str(deployment.state),
        "createdAt": deployment.created_at,
        "publishedAt": deployment.latest_published_at,
        "persistedStatus": deployment.persisted_status,
        "rootNames": list(deployment.root_names),
        "physicalRelationNames": list(deployment.physical_relation_names),
        "activeBindingNames": list(deployment.active_binding_names),
        "missingRelationNames": list(deployment.missing_physical_relation_names),
        "modelCount": len(model_relations),
        "relationCount": len(deployment.physical_relation_names),
        "rows": totals.rows,
        "bytes": totals.bytes,
    }


def _model_payloads(
    *,
    deployment: DeploymentSummary,
    live_by_logical: Mapping[str, str],
    storage: Mapping[str, RelationStorage],
) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    staged_relation: str
    for staged_relation in _model_relation_names(deployment.physical_relation_names):
        logical_name: str = logical_name_from_physical_name(staged_relation)
        live_relation: str | None = live_by_logical.get(logical_name)
        staged_storage: RelationStorage = storage.get(staged_relation, RelationStorage())
        live_storage: RelationStorage | None = (
            None if live_relation is None else storage.get(live_relation, RelationStorage())
        )
        payloads.append(
            {
                "logicalName": logical_name,
                "stagedRelation": staged_relation,
                "stagedRows": staged_storage.rows,
                "stagedBytes": staged_storage.bytes,
                "liveRelation": live_relation,
                "liveDeploymentId": _deployment_id_or_none(live_relation),
                "liveRows": None if live_storage is None else live_storage.rows,
                "isActive": live_relation == staged_relation,
                "isNew": live_relation is None,
            }
        )
    return payloads


def _would_orphan_payload(
    *,
    deployment: DeploymentSummary,
    live_by_logical: Mapping[str, str],
    storage: Mapping[str, RelationStorage],
    models: list[dict[str, object]],
) -> dict[str, object]:
    """Relations the current active bindings would release if this deployment is promoted."""

    replaced_logical_names: set[str] = {
        str(model["logicalName"]) for model in models if model["isActive"] is False
    }
    released: tuple[str, ...] = tuple(
        sorted(
            physical_name
            for logical_name, physical_name in live_by_logical.items()
            if logical_name in replaced_logical_names
        )
    )
    totals: RelationStorage = _storage_total(relation_names=released, storage=storage)
    return {
        "relationCount": 0 if deployment.active_binding_names else len(released),
        "bytes": 0 if deployment.active_binding_names else totals.bytes,
    }


def _model_relation_names(relation_names: tuple[str, ...]) -> tuple[str, ...]:
    """Deployment relations that receive a stable view; landing views are excluded."""

    return tuple(
        relation_name
        for relation_name in relation_names
        if not logical_name_from_physical_name(relation_name).startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        )
    )


def _storage_total(
    *, relation_names: tuple[str, ...], storage: Mapping[str, RelationStorage]
) -> RelationStorage:
    rows: int = 0
    byte_count: int = 0
    relation_name: str
    for relation_name in relation_names:
        entry: RelationStorage = storage.get(relation_name, RelationStorage())
        rows += entry.rows
        byte_count += entry.bytes
    return RelationStorage(rows=rows, bytes=byte_count)


def _deployment_id_or_none(physical_name: str | None) -> str | None:
    if physical_name is None or not is_deployment_physical_name(physical_name):
        return None
    return deployment_id_from_physical_name(physical_name)


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0
