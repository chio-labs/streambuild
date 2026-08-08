"""Resolve deployment diff endpoints and compare their live physical relations."""

import re
from dataclasses import dataclass

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE
from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterDeploymentRecord,
    AdapterQueryResult,
    CatalogColumn,
    CatalogRelation,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    DESIRED_OBJECT_TYPE_VIEW,
)
from streambuild.executor.deployment.constants import (
    ACTIVE_DEPLOYMENT_DIFF_ENDPOINT,
    EXPLICIT_DEPLOYMENT_DIFF_ENDPOINT_COUNT,
)
from streambuild.executor.deployment.exceptions import DeploymentDiffError
from streambuild.executor.deployment.models import (
    DeploymentDiffColumn,
    DeploymentDiffRelation,
    DeploymentDiffRequest,
    DeploymentDiffResult,
)
from streambuild.executor.deployment.types import DeploymentDiffStatus


@dataclass(frozen=True)
class _EndpointRelation:
    database: str
    logical_name: str
    physical_name: str


def execute_diff(
    *, request: DeploymentDiffRequest, client: AdapterConnection
) -> DeploymentDiffResult:
    """Resolve both endpoints and compare schemas and row counts."""

    _validate_identifier(request.database)
    _validate_identifier(request.metadata_database)
    from_endpoint, to_endpoint = _parse_comparison(request.comparison)
    inventory: AdapterDeploymentInventory = client.load_deployment_inventory(
        request.metadata_database
    )
    managed_state: InspectedManagedTableState = client.inspect_managed_table_state(request.database)
    from_relations: dict[tuple[str, str], _EndpointRelation] = _endpoint_relations(
        endpoint=from_endpoint,
        inventory=inventory,
        managed_state=managed_state,
        default_database=request.database,
    )
    to_relations: dict[tuple[str, str], _EndpointRelation] = _endpoint_relations(
        endpoint=to_endpoint,
        inventory=inventory,
        managed_state=managed_state,
        default_database=request.database,
    )
    relation_keys: tuple[tuple[str, str], ...] = tuple(
        sorted(set(from_relations) | set(to_relations))
    )
    catalog_databases: set[str] = set()
    for database, _logical_name in relation_keys:
        catalog_databases.add(database)
    catalogs: dict[str, CatalogSnapshot] = {}
    for database in sorted(catalog_databases):
        catalogs[database] = client.load_catalog(database)
    return DeploymentDiffResult(
        database=request.database,
        from_endpoint=from_endpoint,
        to_endpoint=to_endpoint,
        relations=tuple(
            _compare_relation(
                database=database,
                logical_name=logical_name,
                from_relation=from_relations.get((database, logical_name)),
                to_relation=to_relations.get((database, logical_name)),
                catalogs=catalogs,
                client=client,
            )
            for database, logical_name in relation_keys
        ),
    )


def _parse_comparison(comparison: str) -> tuple[str, str]:
    parts: tuple[str, ...] = tuple(comparison.split(":"))
    if len(parts) == 1 and parts[0]:
        endpoints: tuple[str, str] = ACTIVE_DEPLOYMENT_DIFF_ENDPOINT, parts[0]
    elif len(parts) == EXPLICIT_DEPLOYMENT_DIFF_ENDPOINT_COUNT and all(parts):
        endpoints = parts[0], parts[1]
    else:
        raise DeploymentDiffError("deployment diff expects DEPLOYMENT or FROM:TO")
    if endpoints[0] == endpoints[1]:
        raise DeploymentDiffError("deployment diff endpoints must be different")
    return endpoints


def _endpoint_relations(
    *,
    endpoint: str,
    inventory: AdapterDeploymentInventory,
    managed_state: InspectedManagedTableState,
    default_database: str,
) -> dict[tuple[str, str], _EndpointRelation]:
    if endpoint == ACTIVE_DEPLOYMENT_DIFF_ENDPOINT:
        if not managed_state.active_bindings:
            raise DeploymentDiffError("deployment diff endpoint 'active' has no stable bindings")
        return {
            (binding.database, binding.logical_name): _EndpointRelation(
                database=binding.database,
                logical_name=binding.logical_name,
                physical_name=binding.physical_name,
            )
            for binding in managed_state.active_bindings
        }
    deployment: AdapterDeploymentRecord | None = next(
        (candidate for candidate in inventory.deployments if candidate.deployment_id == endpoint),
        None,
    )
    if deployment is None:
        raise DeploymentDiffError(f"Unknown deployment diff endpoint '{endpoint}'")
    if deployment.status == VIRTUAL_DEPLOYMENT_STATUS_INCOMPLETE:
        raise DeploymentDiffError(f"Deployment diff endpoint '{endpoint}' is incomplete")
    relations: dict[tuple[str, str], _EndpointRelation] = {}
    for mapping in deployment.prepared_object_mappings:
        if mapping.logical_key.object_type not in {
            DESIRED_OBJECT_TYPE_TABLE,
            DESIRED_OBJECT_TYPE_VIEW,
        }:
            continue
        database: str = mapping.logical_key.database or default_database
        relations[(database, mapping.logical_key.name)] = _EndpointRelation(
            database=database,
            logical_name=mapping.logical_key.name,
            physical_name=mapping.physical_name,
        )
    if not relations:
        raise DeploymentDiffError(f"Deployment diff endpoint '{endpoint}' has no model relations")
    return relations


def _compare_relation(
    *,
    database: str,
    logical_name: str,
    from_relation: _EndpointRelation | None,
    to_relation: _EndpointRelation | None,
    catalogs: dict[str, CatalogSnapshot],
    client: AdapterConnection,
) -> DeploymentDiffRelation:
    from_catalog: CatalogRelation | None = _catalog_relation(
        endpoint_relation=from_relation,
        catalogs=catalogs,
    )
    same_physical_relation: bool = (
        from_relation is not None
        and to_relation is not None
        and from_relation.database == to_relation.database
        and from_relation.physical_name == to_relation.physical_name
    )
    to_catalog: CatalogRelation | None = (
        from_catalog
        if same_physical_relation
        else _catalog_relation(endpoint_relation=to_relation, catalogs=catalogs)
    )
    from_columns: tuple[DeploymentDiffColumn, ...] = _diff_columns(from_catalog)
    to_columns: tuple[DeploymentDiffColumn, ...] = _diff_columns(to_catalog)
    from_row_count: int | None = _row_count(
        relation=from_catalog,
        database=database,
        client=client,
    )
    to_row_count: int | None = (
        from_row_count
        if same_physical_relation
        else _row_count(
            relation=to_catalog,
            database=database,
            client=client,
        )
    )
    return DeploymentDiffRelation(
        database=database,
        logical_name=logical_name,
        status=_diff_status(
            from_relation=from_relation,
            to_relation=to_relation,
            from_catalog=from_catalog,
            to_catalog=to_catalog,
            from_columns=from_columns,
            to_columns=to_columns,
            from_row_count=from_row_count,
            to_row_count=to_row_count,
        ),
        from_physical_name=None if from_relation is None else from_relation.physical_name,
        to_physical_name=None if to_relation is None else to_relation.physical_name,
        from_columns=from_columns,
        to_columns=to_columns,
        from_row_count=from_row_count,
        to_row_count=to_row_count,
    )


def _catalog_relation(
    *, endpoint_relation: _EndpointRelation | None, catalogs: dict[str, CatalogSnapshot]
) -> CatalogRelation | None:
    return (
        None
        if endpoint_relation is None
        else catalogs[endpoint_relation.database].relation(endpoint_relation.physical_name)
    )


def _diff_columns(relation: CatalogRelation | None) -> tuple[DeploymentDiffColumn, ...]:
    if relation is None:
        return ()
    return tuple(_diff_column(column) for column in relation.columns)


def _diff_column(column: CatalogColumn) -> DeploymentDiffColumn:
    return DeploymentDiffColumn(
        name=column.name,
        type=column.type,
        default_expression=column.default_expression,
    )


def _row_count(
    *, relation: CatalogRelation | None, database: str, client: AdapterConnection
) -> int | None:
    if relation is None:
        return None
    result: AdapterQueryResult = client.query(
        "SELECT count() AS row_count FROM "
        f"{_quote_identifier(database)}.{_quote_identifier(relation.name)}"
    )
    if len(result.rows) != 1 or len(result.rows[0]) != 1:
        raise DeploymentDiffError(
            f"Deployment diff count for '{relation.name}' returned an unexpected shape"
        )
    value: object = result.rows[0][0]
    if not isinstance(value, int):
        raise DeploymentDiffError(f"Deployment diff count for '{relation.name}' was not an integer")
    return value


def _diff_status(
    *,
    from_relation: _EndpointRelation | None,
    to_relation: _EndpointRelation | None,
    from_catalog: CatalogRelation | None,
    to_catalog: CatalogRelation | None,
    from_columns: tuple[DeploymentDiffColumn, ...],
    to_columns: tuple[DeploymentDiffColumn, ...],
    from_row_count: int | None,
    to_row_count: int | None,
) -> DeploymentDiffStatus:
    if (from_relation is not None and from_catalog is None) or (
        to_relation is not None and to_catalog is None
    ):
        return DeploymentDiffStatus.PHYSICAL_MISSING
    if from_relation is None:
        return DeploymentDiffStatus.ADDED
    if to_relation is None:
        return DeploymentDiffStatus.REMOVED
    if from_columns != to_columns or from_row_count != to_row_count:
        return DeploymentDiffStatus.CHANGED
    return DeploymentDiffStatus.UNCHANGED


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return f"`{value}`"


def _validate_identifier(value: str) -> None:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
        raise DeploymentDiffError(f"Deployment diff cannot query invalid identifier '{value}'")
