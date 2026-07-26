from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewCandidate,
    JanitorPreviewResult,
    JanitorRequest,
)


def execute_janitor_for_managed_table_state(
    *,
    request: JanitorRequest,
    client: AdapterConnection,
    managed_table_state: InspectedManagedTableState,
) -> JanitorPreviewResult | JanitorApplyResult:
    if request.apply:
        return _apply_janitor(
            client=client,
            database=request.database,
            metadata_database=request.metadata_database,
            retention_days=request.retention_days,
            managed_table_state=managed_table_state,
        )
    return _preview_janitor(
        client=client,
        database=request.database,
        metadata_database=request.metadata_database,
        retention_days=request.retention_days,
        managed_table_state=managed_table_state,
    )


def _preview_janitor(
    *,
    client: AdapterConnection,
    database: str,
    metadata_database: str,
    retention_days: int,
    managed_table_state: InspectedManagedTableState,
) -> JanitorPreviewResult:
    from datetime import UTC, datetime, timedelta

    from streambuild.compiler.metadata_state.models import DeploymentRecord
    from streambuild.executor.janitor._helpers.metadata import (
        load_deployments,
        load_latest_publish_times,
    )

    deployments: tuple[DeploymentRecord, ...] = load_deployments(
        client=client,
        metadata_database=metadata_database,
    )
    published_at_by_deployment: dict[str, datetime] = load_latest_publish_times(
        client=client,
        metadata_database=metadata_database,
    )
    active_deployment_ids: set[str] = {
        deployment_id_from_physical_name(binding.physical_name)
        for binding in managed_table_state.active_bindings
        if is_deployment_physical_name(binding.physical_name)
    }
    retention_cutoff: datetime = datetime.now(tz=UTC) - timedelta(days=retention_days)

    candidates: list[JanitorPreviewCandidate] = []
    deployment: DeploymentRecord
    for deployment in sorted(deployments, key=lambda value: value.created_at, reverse=True):
        logical_view_names: tuple[str, ...] = tuple(
            sorted(
                mapping.logical_key.name
                for mapping in deployment.prepared_object_mappings
                if mapping.logical_key.object_type == DESIRED_OBJECT_TYPE_TABLE
                and mapping.logical_key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            )
        )
        physical_object_names: tuple[str, ...] = tuple(
            sorted(mapping.physical_name for mapping in deployment.prepared_object_mappings)
        )
        if deployment.deployment_id in active_deployment_ids:
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason="currently active",
                )
            )
            continue
        published_at: datetime | None = published_at_by_deployment.get(deployment.deployment_id)
        if published_at is not None and published_at >= retention_cutoff:
            candidates.append(
                JanitorPreviewCandidate(
                    deployment_id=deployment.deployment_id,
                    created_at=deployment.created_at,
                    status=deployment.status,
                    logical_view_names=logical_view_names,
                    physical_object_names=physical_object_names,
                    deletable=False,
                    reason=f"published within retention window ({retention_days} days)",
                )
            )
            continue
        reason: str = (
            f"published before retention window ({retention_days} days)"
            if published_at is not None
            else "stale unpublished deployment"
        )
        candidates.append(
            JanitorPreviewCandidate(
                deployment_id=deployment.deployment_id,
                created_at=deployment.created_at,
                status=deployment.status,
                logical_view_names=logical_view_names,
                physical_object_names=physical_object_names,
                deletable=True,
                reason=reason,
            )
        )

    return JanitorPreviewResult(
        database=database,
        retention_days=retention_days,
        candidates=tuple(candidates),
    )


def _apply_janitor(
    *,
    client: AdapterConnection,
    database: str,
    metadata_database: str,
    retention_days: int,
    managed_table_state: InspectedManagedTableState,
) -> JanitorApplyResult:
    preview_result: JanitorPreviewResult = _preview_janitor(
        client=client,
        database=database,
        metadata_database=metadata_database,
        retention_days=retention_days,
        managed_table_state=managed_table_state,
    )
    deleted_deployment_ids: list[str] = []
    deleted_object_names: list[str] = []
    candidate: JanitorPreviewCandidate
    for candidate in preview_result.candidates:
        if not candidate.deletable:
            continue
        object_name: str
        for object_name in candidate.physical_object_names:
            client.command(f"DROP TABLE IF EXISTS {database}.{object_name} SYNC")
            deleted_object_names.append(object_name)
        deleted_deployment_ids.append(candidate.deployment_id)

    return JanitorApplyResult(
        database=database,
        retention_days=retention_days,
        deleted_deployment_ids=tuple(deleted_deployment_ids),
        deleted_object_names=tuple(deleted_object_names),
    )
