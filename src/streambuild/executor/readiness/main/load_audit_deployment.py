"""Load the deployment record audited by a backfill readiness check."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterDeploymentRecord
from streambuild.compiler.compile.models import ObjectKey
from streambuild.executor.readiness.models import LoadedAuditDeployment


def load_audit_deployment(
    *,
    client: AdapterConnection,
    metadata_database: str,
    deployment_id: str,
) -> LoadedAuditDeployment:
    """Load the persisted deployment metadata needed for audit."""

    matching: tuple[AdapterDeploymentRecord, ...] = tuple(
        deployment
        for deployment in client.load_deployment_inventory(metadata_database).deployments
        if deployment.deployment_id == deployment_id
    )
    if not matching:
        return LoadedAuditDeployment(
            deployment_id=deployment_id,
            created_at="",
            status="metadata_missing",
            replay_lineage_mode=None,
            warning_codes=(),
            root_keys=(),
            prepared_object_mappings=(),
        )
    deployment: AdapterDeploymentRecord = matching[0]
    return LoadedAuditDeployment(
        deployment_id=deployment_id,
        created_at=deployment.created_at,
        status=deployment.status,
        replay_lineage_mode=deployment.replay_lineage_mode,
        warning_codes=deployment.warning_codes,
        root_keys=tuple(
            ObjectKey(database=key.database, object_type=key.object_type, name=key.name)
            for key in deployment.selected_root_keys
        ),
        prepared_object_mappings=tuple(
            (
                ObjectKey(
                    database=mapping.logical_key.database,
                    object_type=mapping.logical_key.object_type,
                    name=mapping.logical_key.name,
                ),
                mapping.physical_name,
            )
            for mapping in deployment.prepared_object_mappings
        ),
    )
